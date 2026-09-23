/**
 * WorkBuddy 云模型：免密钥的大模型调用。
 *
 * 为什么生成要发生在浏览器里
 * --------------------------------------------------------------------------
 * 云端的 LLM 通道用 `publishableKey` 鉴权，服务端校验的是**浏览器 Origin 是否
 * 等于应用的发布域名**。Python 后端既没有 Origin，也不该代持这份凭据（自建
 * BFF 去转发是明确禁止的用法）。所以：
 *
 *   后端负责 检索 + 组装提示词（`/api/ask/plan`）→ 浏览器拿 messages 去生成
 *   → 生成完送回后端存档（`/api/ask/save`）。
 *
 * 提示词只在后端 `server/services/llm/prompt.py` 一份，前端不复制模板。
 *
 * 桌面版能用吗
 * --------------------------------------------------------------------------
 * 不能。桌面版跑在 `http://127.0.0.1:8760`，Origin 与发布域名不符，调用会被
 * 服务端拒掉（`auth_` 一类的错误）。这不是 bug，是这条通道的鉴权方式决定的。
 * 界面上要如实说明，并且**失败时回落到内置模型**，而不是把错误甩给用户。
 */

import {
  createWorkBuddyCloud,
  type ChatCompletionRequestMessage,
} from '@tencent-ai/workbuddy-cloud-sdk'

/**
 * 这两个值来自开通云服务时返回的 `publicConfig`，是**唯一**允许写进前端的配置。
 *
 * 它们标识的是"哪个应用"，本身不带任何权限；真正有效的约束在服务端那条
 * 精确 Origin 匹配上。若这个应用被重建（换了新的 `wbapp_` id），
 * 这里必须一起换——写死在源码里已是不得已，好在只有这一处。
 */
const CLOUD_ENDPOINT = 'https://life-mentor-54743.app.workbuddy.host'
const CLOUD_PUBLISHABLE_KEY =
  'wbpk_TtIpaJXRbD6JDaFCmYYEqy_5zfa20mS1B9MDULYALG6r50gRc3GniJM'

export const cloud = createWorkBuddyCloud({
  endpoint: CLOUD_ENDPOINT,
  publishableKey: CLOUD_PUBLISHABLE_KEY,
})

export interface CloudModel {
  id: string
  /** 显示名；服务端没配名字时用 id */
  name: string
  /** 目录标的那一个。偏好里一个都没中时才轮到它 */
  isDefault?: boolean
}

/**
 * 偏好的模型，按顺序试。
 *
 * 目录的第一条是 `auto`（"自动为每个任务匹配最优模型"），省心但输出不稳定——
 * 而这里要的是长篇中文说理，模型一换，同一句话的深浅能差一截。所以宁可
 * 指定一个强的。**这只是偏好，不是硬编码**：目录里一个都不中时，下面会退回
 * 目录标的那一个（再不行就第一条），不会因此调不通。
 */
const PREFERRED_MODELS = ['deepseek-v4-pro', 'glm-5.3', 'kimi-k3-1']

/**
 * 云端模型目录。
 *
 * 目录是会变的（上下线、调价、换默认），所以每次进求教页都重新拉一次，
 * 不做持久化缓存——把一个已经下线的模型 id 留在浏览器里，用户只会看到报错。
 */
export async function listCloudModels(): Promise<CloudModel[]> {
  const models = await cloud.llm.models.list()
  return models
    .filter(model => model.disabled !== true && model.enabled !== false)
    .map(model => ({
      id: model.id,
      name: model.name || model.id,
      isDefault: model.isDefault === true,
    }))
}

/** 从目录里挑一个来用：先按偏好，再退回目录默认，最后取第一条。 */
export function pickCloudModel(models: CloudModel[]): CloudModel | null {
  for (const id of PREFERRED_MODELS) {
    const hit = models.find(model => model.id === id)
    if (hit) return hit
  }
  return models.find(model => model.isDefault) ?? models[0] ?? null
}

/**
 * 流式生成，逐段吐出正文。
 *
 * 云端只支持 `stream: true`，没有非流式（`stream: false` 会被 SDK 直接拒掉，
 * 连请求都不发）。所以哪怕是"一次性要完整结果"的用法，也只能自己把
 * SSE 的片段拼起来——这里就是那个拼接处。
 */
export async function* streamCloudChat(
  modelId: string,
  messages: { role: string; content: string }[],
  signal?: AbortSignal,
): AsyncGenerator<string, void, unknown> {
  const stream = await cloud.llm.chat.completions.create({
    model: modelId,
    messages: messages as ChatCompletionRequestMessage[],
    stream: true,
    ...(signal ? { signal } : {}),
  })
  for await (const chunk of stream) {
    const delta = chunk.choices[0]?.delta
    // 第一帧是 role 占位（content 为空串），跳过它，别往正文里塞空行
    if (delta?.content) yield delta.content
  }
}

/** 云端错误的机器可读归类，供界面翻译成人话。 */
export type CloudErrorKind =
  | 'auth'
  | 'quota'
  | 'unavailable'
  | 'bad_request'
  | 'internal'
  | 'unknown'

export interface CloudErrorInfo {
  kind: CloudErrorKind
  /** 上游给的原因原文，用于排查；不直接给用户看大段堆栈 */
  detail: string
}

/**
 * 把云端异常归成几类。
 *
 * 按错误码前缀分（`request_` / `auth_` / `quota_` / `gateway_|model_` /
 * `internal_`），而不是看 HTTP 状态码——同一件事在不同网关上状态码并不一致。
 */
export function cloudErrorInfo(error: unknown): CloudErrorInfo {
  const detail = error instanceof Error ? error.message : String(error)
  const code = String(
    (error as { error?: { code?: string | null } } | null)?.error?.code ?? '',
  )
  if (code.startsWith('auth_')) return { kind: 'auth', detail }
  if (code.startsWith('quota_')) return { kind: 'quota', detail }
  if (code.startsWith('gateway_') || code.startsWith('model_')) {
    return { kind: 'unavailable', detail }
  }
  if (code.startsWith('request_')) return { kind: 'bad_request', detail }
  if (code.startsWith('internal_')) return { kind: 'internal', detail }
  return { kind: 'unknown', detail }
}

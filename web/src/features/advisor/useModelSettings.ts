import { useCallback, useState } from 'react'
import type { LLMEndpoint } from '../../api/types'

/**
 * 用内置的默认模型、自己填的端点，还是 WorkBuddy 云模型（免密钥）。
 *
 * `cloud` 只在**发布域名**下才真的走得通：云端按浏览器 Origin 鉴权，
 * 桌面版（`127.0.0.1`）与本地开发服务器都会被拒。界面允许选它，
 * 但失败时必须回落到内置模型，不能让用户卡在报错上。
 */
export type ModelMode = 'default' | 'custom' | 'cloud'

/**
 * 存在本地的那份设置。
 *
 * ``Required<LLMEndpoint>``：契约里那三个字段是**可以为空**的（它描述的是
 * 请求体，只填一半会被后端视同没填），但存进 localStorage 的这一份是"已定稿"
 * 的字符串，界面直接把它当输入框的 value。形状仍然来自生成物，只是收紧了可选性。
 */
export interface ModelSettings extends Required<LLMEndpoint> {
  mode: ModelMode
}

/**
 * 模型选择存在浏览器 localStorage 里，而不是存到后端：
 *
 * - 打包后的程序可能装在 Program Files 这类不可写目录，落盘还要处理权限；
 * - API Key 是本机用户自己的东西，存在自己浏览器里最直白，也便于随时清掉；
 * - 后端只在一次请求内使用它，不落盘、不回显。
 *
 * 代价是"换一台机器要重填"，这与"Key 不被别人拿到"相比是划算的。
 */
const STORAGE_KEY = 'rsds.model-settings'

export const EMPTY_SETTINGS: ModelSettings = {
  mode: 'default',
  base_url: '',
  api_key: '',
  model: '',
}

/** 自定义模式是否已填全。只填一半视同没填——后端也会这么判。 */
export function isComplete(settings: ModelSettings): boolean {
  return settings.base_url.trim() !== '' && settings.api_key.trim() !== ''
}

/**
 * 把设置转成请求载荷。返回 null 表示"这次用内置默认模型"，
 * 于是请求里根本不会出现 llm 字段。
 */
export function toPayload(settings: ModelSettings): LLMEndpoint | null {
  if (settings.mode !== 'custom' || !isComplete(settings)) return null
  return {
    base_url: settings.base_url.trim(),
    api_key: settings.api_key.trim(),
    model: settings.model.trim(),
  }
}

function read(): ModelSettings {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return EMPTY_SETTINGS
    const parsed = JSON.parse(raw) as Partial<ModelSettings>
    return {
      mode:
        parsed.mode === 'custom' ? 'custom' : parsed.mode === 'cloud' ? 'cloud' : 'default',
      base_url: typeof parsed.base_url === 'string' ? parsed.base_url : '',
      api_key: typeof parsed.api_key === 'string' ? parsed.api_key : '',
      model: typeof parsed.model === 'string' ? parsed.model : '',
    }
  } catch {
    // 无痕模式、被禁用、或存的内容坏了：一律当作没配过，不影响问答本身
    return EMPTY_SETTINGS
  }
}

function write(settings: ModelSettings): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {
    // 写不进去就只在本次会话内生效，不必打扰用户
  }
}

export function useModelSettings() {
  const [settings, setSettings] = useState<ModelSettings>(read)

  const update = useCallback((patch: Partial<ModelSettings>) => {
    setSettings(prev => {
      const next = { ...prev, ...patch }
      write(next)
      return next
    })
  }, [])

  const reset = useCallback(() => {
    setSettings(EMPTY_SETTINGS)
    write(EMPTY_SETTINGS)
  }, [])

  return { settings, update, reset, payload: toPayload(settings) }
}

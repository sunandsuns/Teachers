import { useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type AskContext, type AskResponse } from '../../api/client'
import { useModelSettings } from './useModelSettings'
import { useI18n } from '../../i18n'
import {
  cloudErrorInfo,
  listCloudModels,
  pickCloudModel,
  streamCloudChat,
  type CloudModel,
} from '../../lib/cloud'

export interface Exchange {
  question: string
  answer: AskResponse
}

/** 追问时带上前几轮。给了模型才接得上上文；给多了只是白占请求体，
 * 后端也只认最近几轮（见 `prompt.MAX_HISTORY_TURNS`）。 */
const FOLLOW_UP_TURNS = 3

/**
 * 求教的全部状态与副作用。
 *
 * 这是这一块里**唯一**碰网络的地方。页面只拿结果去渲染，所以：
 *   · 想换一套界面（气泡 / 文档流 / 分栏），不必读懂任何请求逻辑；
 *   · 想测"云端失败会不会回落"，也不必渲染一棵组件树。
 *
 * 降级链是这里最要紧的不变量：
 *   云端（选了才有）→ 内置默认模型 → 本地检索
 * 任何一环失败都**写清原因再往下走**，而不是把错误吞掉——
 * 用户必须知道"为什么这次答案看着不一样"。
 */
export function useAdvisor() {
  const { lang, t } = useI18n()
  // 支持 ?q= 预填：「回响」页的「再问一次」就是这么跳过来的，
  // 让人能接着旧问题追问，而不是重新打一遍字。
  const [params] = useSearchParams()
  const [question, setQuestion] = useState(() => params.get('q') ?? '')
  // 话题：首问留空让后端新开一个，之后每次都用响应里回传的那个。
  // 从「回响」点"再问一次"跳过来时会带 ?topic=…，于是这次追问仍归在原话题下。
  const [conversationId, setConversationId] = useState(() => params.get('topic') ?? '')
  const [history, setHistory] = useState<Exchange[]>([])
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /** 云模型那条路是流式的：正文边生成边渲染，所以单独存一份"正在生成"。 */
  const [streaming, setStreaming] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const { settings, update, payload } = useModelSettings()

  // 只有"选了自定义且填全了"才会真的换模型。按钮上如实区分三种情况：
  // 选了自定义却还没填时若直接显示"默认"，用户会以为自己白点了那一下。
  const modelLabel =
    settings.mode === 'cloud'
      ? t('ask.model.cloud')
      : settings.mode === 'default'
        ? t('ask.model.default')
        : payload !== null
          ? t('ask.model.custom')
          : t('ask.model.incomplete')

  function scrollToBottom() {
    requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }))
  }

  /** 挑一个云端模型。目录是会变的，所以每次都现拉，不缓存。 */
  async function resolveCloudModel(): Promise<CloudModel | null> {
    try {
      return pickCloudModel(await listCloudModels())
    } catch (err) {
      setError(`${t('ask.cloud.unavailable')}（${cloudErrorInfo(err).detail}）`)
      return null
    }
  }

  /**
   * 走云端生成。返回 false 表示这条路这次没走通，调用方会退回内置模型——
   * 云模型只是"更好"的一条路，不该变成"唯一"的一条路。
   */
  async function askWithCloud(q: string, context: AskContext): Promise<boolean> {
    const model = await resolveCloudModel()
    if (!model) return false
    let planned
    try {
      planned = await api.planAsk(q, 5, lang, context)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ask.failed'))
      return false
    }
    try {
      let text = ''
      setStreaming('')
      for await (const piece of streamCloudChat(model.id, planned.messages)) {
        text += piece
        setStreaming(text)
      }
      setStreaming(null)
      if (!text.trim()) {
        setError(t('ask.cloud.empty'))
        return false
      }
      const saved = await api.saveAsk(
        q,
        text,
        model.name,
        planned.retrieved_count,
        planned.conversation_id,
      )
      setHistory(prev => [...prev, { question: q, answer: saved }])
      setConversationId(saved.conversation_id)
      return true
    } catch (err) {
      setStreaming(null)
      const info = cloudErrorInfo(err)
      setError(`${t(`ask.cloud.${info.kind}`)}（${info.detail}）`)
      return false
    }
  }

  async function submit(q: string) {
    const trimmed = q.trim()
    if (!trimmed || asking) return
    setAsking(true)
    setError(null)
    setStreaming(null)
    // 带上最近几轮：追问要接得上刚才的话
    const context: AskContext = {
      conversationId,
      history: history.slice(-FOLLOW_UP_TURNS).map(ex => ({
        question: ex.question,
        answer: ex.answer.answer,
      })),
    }
    try {
      if (settings.mode === 'cloud' && (await askWithCloud(trimmed, context))) {
        setQuestion('')
        scrollToBottom()
        return
      }
      // 云端没走通（或压根没选云端）时，照原路走内置/自定义模型。
      // 上面已经把原因写进 error，这里不再覆盖——用户要看到"为什么降级了"。
      const answer = await api.ask(trimmed, 5, payload, lang, context)
      setHistory(prev => [...prev, { question: trimmed, answer }])
      // 首问时后端会新开一个话题，这里接住它——后面几问才归得到同一个话题下
      setConversationId(answer.conversation_id)
      setQuestion('')
      scrollToBottom()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ask.failed'))
    } finally {
      setAsking(false)
    }
  }

  return {
    question,
    setQuestion,
    history,
    asking,
    error,
    streaming,
    settings,
    update,
    modelLabel,
    submit,
    bottomRef,
  }
}

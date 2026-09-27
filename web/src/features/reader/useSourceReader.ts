import { useCallback, useEffect, useRef, useState } from 'react'
import { api, peek, type SourceChunk } from '../../api/client'

export interface SourceReader {
  /** 已累加的原典正文 */
  text: string
  /** 本次加载的起始位置（从检索结果跳转时不为 0） */
  startOffset: number
  /** 全书总字数 */
  total: number
  /** 单块大小（用于判断这本书是否需要分页） */
  chunkSize: number
  hasMore: boolean
  loading: boolean
  error: string | null
  loadMore: () => void
  /** 回到开头重新读 */
  restart: () => void
}

/** 正文状态。`loading` / `error` 不在这里：它们由各自的 `useState` 管，
 *  与"读到了多少字"是两回事。 */
interface SourceState {
  text: string
  startOffset: number
  total: number
  chunkSize: number
  hasMore: boolean
}

const EMPTY: SourceState = {
  text: '',
  startOffset: 0,
  total: 0,
  chunkSize: 0,
  hasMore: false,
}

/**
 * 把一块正文并进当前状态。
 *
 * **两条来源共用这一份**：网络响应（`fetchChunk`）与缓存快照（首帧）。这是
 * 这个钩子里最容易写坏的一行——`offset === 0` 是"从头读/重读"，要**替换**；
 * 否则是"往下翻"，要**追加**。两处各写一遍的话，写歪的那一份会表现成
 * 正文里凭空多出一段重复，而屏幕上只是"读起来怪怪的"，不报错。
 *
 * `prevText` 为空时两种分支结果相同（`'' + content`），所以首帧从任意
 * offset 恢复都对。
 */
function stateFromChunk(chunk: SourceChunk, offset: number, prevText: string): SourceState {
  return {
    text: offset === 0 ? chunk.content : prevText + chunk.content,
    startOffset: offset,
    total: chunk.total,
    chunkSize: chunk.limit,
    hasMore: chunk.has_more,
  }
}

/**
 * 原典分块读取。
 *
 * 《资治通鉴》全文约 310 万字，一次性渲染会让浏览器卡死，
 * 因此后端按块返回、这里按块累加。
 *
 * `initialOffset` 用于「寻章」页跳转——命中段落在第 12 万字时，
 * 从 0 开始逐块加载毫无意义，直接从该位置取一块即可。
 *
 * ## 首帧的缓存快照
 *
 * 只有切到原典页签才真去拉正文（笔记页签不该为它付一次请求），所以
 * `active` 每次从 false 翻到 true 都是一次"重新开始"。原先那一下必然先
 * `loading = true`，于是切回原典页签时先闪一帧"正在加载原典正文"——
 * 哪怕那块正文就在 GET 缓存里躺着。
 *
 * 这里**与 `useAsync` 的做法不同**：`useAsync` 命中缓存后照常发请求（它的
 * `data` 是整体替换语义，多一次请求只是白跑一趟）。原典的 `text` 是**累加**
 * 的（见 `stateFromChunk`），命中之后若再发一次同一个 `offset` 的请求，回来
 * 的那一块会被追加到刚恢复的正文后面——屏幕上就是整整一段重复。所以命中
 * 即不再请求。
 *
 * 不这么做会不会读到旧正文？不会：正文来自随包发布的语料文件，走 `/books/`
 * 那条 5 分钟 TTL；`peek` 与 `request` 共用同一个过期判据，过期后 `peek`
 * 返回 `undefined`，自然回到请求这条路。
 */
export function useSourceReader(
  bookId: string,
  active: boolean,
  initialOffset = 0,
): SourceReader {
  const [state, setState] = useState<SourceState>(EMPTY)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 用于丢弃"上一本书 / 上一次跳转"的迟到响应，避免错位的正文被拼进来
  const requestId = useRef(0)

  const fetchChunk = useCallback(
    async (offset: number) => {
      const current = ++requestId.current
      setLoading(true)
      setError(null)
      try {
        const chunk: SourceChunk = await api.getSource(bookId, offset)
        if (current !== requestId.current) return
        setState(prev => stateFromChunk(chunk, offset, prev.text))
      } catch (err) {
        if (current !== requestId.current) return
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (current === requestId.current) setLoading(false)
      }
    },
    [bookId],
  )

  useEffect(() => {
    // 自增这个数，让"上一次"的响应回来后认不出自己（`current !== requestId.current`）
    requestId.current += 1
    setError(null)

    if (!active) {
      setState(EMPTY)
      setLoading(false)
      return
    }

    const cached = peek.getSource(bookId, initialOffset)
    if (cached) {
      // 命中：首帧就是这块正文，不进 loading 分支。`requestId` 已经自增过，
      // 所以即便有更早的请求在飞，它的响应回来也会被丢掉。
      setState(stateFromChunk(cached, initialOffset, ''))
      setLoading(false)
      return
    }

    setState(EMPTY)
    setLoading(false)
    void fetchChunk(initialOffset)
  }, [active, bookId, initialOffset, fetchChunk])

  return {
    ...state,
    loading,
    error,
    loadMore: () => void fetchChunk(state.startOffset + state.text.length),
    restart: () => void fetchChunk(0),
  }
}

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type SourceChunk } from '../../api/client'

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

const EMPTY = { text: '', startOffset: 0, total: 0, chunkSize: 0, hasMore: false }

/**
 * 原典分块读取。
 *
 * 《资治通鉴》全文约 310 万字，一次性渲染会让浏览器卡死，
 * 因此后端按块返回、这里按块累加。
 *
 * `initialOffset` 用于「寻章」页跳转——命中段落在第 12 万字时，
 * 从 0 开始逐块加载毫无意义，直接从该位置取一块即可。
 */
export function useSourceReader(
  bookId: string,
  active: boolean,
  initialOffset = 0,
): SourceReader {
  const [state, setState] = useState(EMPTY)
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
        setState(prev => ({
          text: offset === 0 ? chunk.content : prev.text + chunk.content,
          startOffset: offset,
          total: chunk.total,
          chunkSize: chunk.limit,
          hasMore: chunk.has_more,
        }))
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
    requestId.current += 1
    setState(EMPTY)
    setError(null)
    setLoading(false)
    if (active) void fetchChunk(initialOffset)
  }, [active, bookId, initialOffset, fetchChunk])

  return {
    ...state,
    loading,
    error,
    loadMore: () => void fetchChunk(state.startOffset + state.text.length),
    restart: () => void fetchChunk(0),
  }
}

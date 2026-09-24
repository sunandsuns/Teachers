import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type BookCandidate, type ShelfBook, type ShelfStatus } from '../../api/client'
import { GUIDE_POLL_MAX, GUIDE_POLL_MS } from './constants'

/**
 * 「我的书架」的数据与动作。
 *
 * 页面只管怎么摆，这里管"摆什么"和"点了之后发生什么"。
 *
 * 三处刻意的设计
 * --------------------------------------------------------------------------
 * 1. **筛选在本地做**，不重新请求。列表一次最多 200 本，在内存里按状态过一遍
 *    是微秒级的；改成每次点药丸都打一次后端，切来切去会明显发顿，而
 *    `counts` 后端已经给了，本地筛出来的数量与它天然一致。
 *
 * 2. **写操作之后重拉一次列表**，而不是在本地把返回值拼进去。加书会补简介、
 *    改状态会动 `updated_at`，本地拼很容易漏字段；重拉一次只花几毫秒，
 *    换来的是"界面上看到的永远和服务端一致"。
 *
 * 3. **导读要轮询**。导读是后端在后台生成的，加书请求返回时 `has_guide` 还是
 *    false。这里每隔几秒回来看一眼，最多看 `GUIDE_POLL_MAX` 次——
 *    封顶是必须的：生成失败时它永远是 false，不封顶就是一个永不停止的轮询。
 */
export function useShelf() {
  const [books, setBooks] = useState<ShelfBook[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [status, setStatusFilter] = useState<ShelfStatus | null>(null)

  /** 轮询计数。手动刷新时归零——用户主动要求看最新，就该重新给满预算。 */
  const polls = useRef(0)

  const load = useCallback(async (options: { resetPolls?: boolean } = {}) => {
    if (options.resetPolls) polls.current = 0
    try {
      const data = await api.listShelf()
      setBooks(data.books)
      setCounts(data.counts)
      setTotal(data.total)
      setError('')
      return data.books
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      return []
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load({ resetPolls: true })
  }, [load])

  /** 还有几本的导读没生成好。 */
  const pendingGuides = useMemo(
    () => books.filter(book => !book.has_guide).length,
    [books],
  )

  useEffect(() => {
    if (pendingGuides === 0) {
      polls.current = 0
      return
    }
    if (polls.current >= GUIDE_POLL_MAX) return
    const timer = window.setTimeout(() => {
      polls.current += 1
      void load()
    }, GUIDE_POLL_MS)
    return () => window.clearTimeout(timer)
  }, [pendingGuides, load])

  const visible = useMemo(
    () => (status ? books.filter(book => book.status === status) : books),
    [books, status],
  )

  const add = useCallback(
    async (candidate: BookCandidate) => {
      const created = await api.addShelfBook(candidate)
      await load({ resetPolls: true })
      return created
    },
    [load],
  )

  const setBookStatus = useCallback(
    async (book: ShelfBook, next: ShelfStatus) => {
      const updated = await api.updateShelfBook(book.id, { status: next })
      // 只换那一条，不重拉整页：改状态是个高频小动作，
      // 整页重拉会让列表闪一下（骨架/重排），而这里没有任何别的字段会变。
      setBooks(current => current.map(item => (item.id === updated.id ? updated : item)))
      setCounts(current => {
        const moved = { ...current }
        moved[book.status] = Math.max(0, (moved[book.status] ?? 1) - 1)
        moved[next] = (moved[next] ?? 0) + 1
        return moved
      })
      return updated
    },
    [],
  )

  const remove = useCallback(
    async (book: ShelfBook) => {
      await api.removeShelfBook(book.id)
      await load()
    },
    [load],
  )

  const submit = useCallback(async (book: ShelfBook) => {
    const updated = await api.submitShelfBook(book.id)
    setBooks(current => current.map(item => (item.id === updated.id ? updated : item)))
    return updated
  }, [])

  const cancelReview = useCallback(async (book: ShelfBook) => {
    const updated = await api.cancelShelfBook(book.id)
    setBooks(current => current.map(item => (item.id === updated.id ? updated : item)))
    return updated
  }, [])

  return {
    books,
    visible,
    counts,
    total,
    loading,
    error,
    status,
    setStatus: setStatusFilter,
    pendingGuides,
    reload: load,
    add,
    setBookStatus,
    remove,
    submit,
    cancelReview,
  }
}

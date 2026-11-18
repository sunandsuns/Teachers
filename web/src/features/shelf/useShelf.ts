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
 *
 *    **轮询要靠 `pollTick` 一轮一轮推**，不能只靠 `pendingGuides`。它是个**数字**，
 *    `load()` 回来之后往往还是同一个值（1 还是 1），依赖没变 effect 就不会再执行，
 *    于是排不出下一支定时器——"最多看 8 次"实际只发生了 1 次：第 4 秒看一眼，
 *    没等到就永远停在那一刻，而模型正常要十几秒才出结果。症状是卡片上
 *    "导读生成中…"一直挂着，等多久都不动，书架上却早就有导读/失败原因了。
 *    所以每跑完一次就 `pollTick + 1`，把 effect 推起来排下一支。
 *
 *    同一个理由，"点重新生成"也不能只重置计数——必须再推一次 `pollTick`。
 *    那一步的用户多半早就把 8 次预算看完了，光把计数归零不会让 effect 重新
 *    执行，新起的后台任务不会被看一眼，"重新生成"就成了一句空话。
 */
export function useShelf() {
  const [books, setBooks] = useState<ShelfBook[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [status, setStatusFilter] = useState<ShelfStatus | null>(null)
  /** 正在手动重新生成导读的那几本。卡片据此显示"生成中"——它刚加进来，
   *  `created_at` 是旧的，光靠时间判不出这次重试。 */
  const [regenerating, setRegenerating] = useState<ReadonlySet<number>>(() => new Set())

  /** 轮询计数。手动刷新时归零——用户主动要求看最新，就该重新给满预算。 */
  const polls = useRef(0)
  /** 每要求轮询一轮就 +1：把下面那个 effect 从"静止"推起来，好排下一支定时器。
   *  没有它，轮询只跑得动第一轮（原因见文件头）。 */
  const [pollTick, setPollTick] = useState(0)

  const load = useCallback(async (options: { resetPolls?: boolean } = {}) => {
    if (options.resetPolls) polls.current = 0
    try {
      const data = await api.listShelf()
      setBooks(data.books)
      setCounts(data.counts)
      setTotal(data.total)
      setError('')
      setRegenerating(current => settledGuides(current, data.books))
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

  /** 还有几本的导读没出结果：既没有导读、也没有失败原因。
   *
   * 把 `guide_error` 有内容的排除掉是必要的——那种书**这一轮已经有结论了**
   * （结论就是失败），它不会自己再变，继续为它轮询是白花预算，还会把后面的
   * 书挤掉。用户点"重新生成"时后端会先把原因清空，它自然又回到这个计数里。 */
  const pendingGuides = useMemo(
    () => books.filter(book => !book.has_guide && !book.guide_error).length,
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
      // 先推一轮再拉：`load()` 回来后 `pendingGuides` 多半没变（还是 1），
      // 依赖不变 effect 就不会重跑，下一支定时器也就排不出来。
      setPollTick(tick => tick + 1)
      void load()
    }, GUIDE_POLL_MS)
    return () => window.clearTimeout(timer)
  }, [pendingGuides, pollTick, load])

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

  /**
   * 重新生成这本书的导读。
   *
   * 三件事的顺序要紧：先标上"生成中"（否则点了按钮界面毫无变化，用户会以为
   * 没点上），再请求，最后**重置轮询预算并踢一脚那个 effect**。
   *
   * 重置是必须的：到这一步的用户，多半早就看过 8 次轮询没等到东西——预算
   * 已经花光，不重置的话新起的后台任务不会被看一眼，"重新生成"就成了一句
   * 空话。再推一轮 `pollTick` 同理：`pendingGuides` 在这前后常常是同一个数
   * （这本书本来就是"没导读、没原因"），光重置计数不会让 effect 重新执行、
   * 排不出下一支定时器。
   */
  const regenerate = useCallback(
    async (book: ShelfBook) => {
      setRegenerating(current => new Set(current).add(book.id))
      try {
        await api.regenerateShelfGuide(book.id)
        await load({ resetPolls: true })
        setPollTick(tick => tick + 1)
      } catch (err) {
        // 请求本身就没发出去（或后端拒了）：别把它一直挂在"生成中"上
        setRegenerating(current => {
          const next = new Set(current)
          next.delete(book.id)
          return next
        })
        throw err
      }
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
    regenerating,
    reload: load,
    add,
    regenerate,
    setBookStatus,
    remove,
    submit,
    cancelReview,
  }
}

/**
 * 把"正在重新生成"的集合收一收：跑完了的（拿到导读，或又失败了一次）就摘掉。
 *
 * 两个判据都不许少。只看 `has_guide` 的话，重试又失败的那本书会永远停在
 * "生成中"——它再也不会变真，而失败原因已经写回来了，那一刻该显示的是原因。
 *
 * 集合没变化时**原样返回**：`load` 会被轮询反复调用，每次都新建一个空集合
 * 会让 `Set` 的引用每几秒变一次，白引一串重渲染。
 */
function settledGuides(
  pending: ReadonlySet<number>,
  books: ShelfBook[],
): ReadonlySet<number> {
  if (pending.size === 0) return pending
  const byId = new Map(books.map(book => [book.id, book]))
  const next = new Set<number>()
  for (const id of pending) {
    const book = byId.get(id)
    // 还在架子上、又没有导读也没有失败原因 → 这一轮还没出结果
    if (book && !book.has_guide && book.guide_error === '') next.add(id)
  }
  return next.size === pending.size ? pending : next
}

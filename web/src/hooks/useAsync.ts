import { useCallback, useEffect, useState } from 'react'

/** 通用异步状态钩子：加载中/错误/数据三态。
 *
 * ``reload`` 是后加的一次"用同一个 loader 再跑一遍"。它靠一个自增的 tick 而不是
 * 让调用方把 loader 包进 ``useCallback``：后者要求每个调用点都记得这件事，
 * 忘一次就是一个每次渲染都重新请求的死循环。
 */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  /** 每次手动刷新自增。它同时是 effect 的依赖——刷新就是"用同一个 loader 再跑一遍"，
   *  所以不必让调用方把 loader 包进 useCallback。 */
  const [tick, setTick] = useState(0)

  const reload = useCallback(() => setTick(value => value + 1), [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    loader()
      .then(result => {
        if (!cancelled) setData(result)
      })
      .catch(err => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { data, error, loading, reload }
}

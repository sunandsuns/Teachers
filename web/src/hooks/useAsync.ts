import { useCallback, useEffect, useRef, useState } from 'react'

/** 通用异步状态钩子：加载中/错误/数据三态。
 *
 * ``reload`` 是后加的一次"用同一个 loader 再跑一遍"。它靠一个自增的 tick 而不是
 * 让调用方把 loader 包进 ``useCallback``：后者要求每个调用点都记得这件事，
 * 忘一次就是一个每次渲染都重新请求的死循环。
 *
 * ## 第三个参数：缓存快照
 *
 * 页面是按路由分包的，**切走再切回会重新挂载**（见 App.tsx 的 lazy）。
 * 挂载即 ``loading = true``，于是"从阅读页退回书架"每次都要先闪一帧骨架屏——
 * 哪怕数据就在 GET 缓存里躺着，只是取它需要等到 effect 跑完。
 *
 * ``peek`` 是**同步**读那份缓存的入口（``api/client.ts`` 导出的那组 ``peek.*``）。
 * 有它做初值时，缓存命中的页面从挂载到稳定**只渲染一次**，骨架屏根本不出现：
 * 初值就是数据，随后 ``setData`` 拿到的是同一个对象引用，React 直接跳过。
 *
 * 不传也行——没进 GET 缓存的接口（后台管理、历史记录、求教）本来就该每次
 * 真请求，它们的 ``peek`` 恒为 ``undefined``，传了也只是摆设。
 */
export function useAsync<T>(
  loader: () => Promise<T>,
  deps: unknown[] = [],
  peek?: () => T | undefined,
) {
  // 初值走 peek：挂载那一刻就知道数据在不在手上，不必先画骨架屏。
  // 两个 useState 各调一次 peek，都是一次 Map 查询，纳秒级，不值得为它
  // 再多引一个变量去协调"数据有、loading 却没有"的中间态。
  const [data, setData] = useState<T | null>(() => peek?.() ?? null)
  const [loading, setLoading] = useState(() => peek?.() === undefined)
  const [error, setError] = useState<string | null>(null)
  /** 每次手动刷新自增。它同时是 effect 的依赖——刷新就是"用同一个 loader 再跑一遍"，
   *  所以不必让调用方把 loader 包进 useCallback。 */
  const [tick, setTick] = useState(0)
  /** 这一次 effect 是被 `reload()` 触发的。刷新**必须忽略缓存快照**，
   *  否则"点一下刷新"会原样返回旧值，按钮看着像坏了。
   *
   *  现有的 reload 调用点全落在不缓存的接口上，所以这一条暂时是防御性的；
   *  但契约上就该如此，不能靠"调用方恰好不缓存"来成立。 */
  const forced = useRef(false)

  const reload = useCallback(() => {
    forced.current = true
    setTick(value => value + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    const cached = forced.current ? undefined : peek?.()
    forced.current = false
    if (cached !== undefined) {
      // 依赖变了而新 key 也有缓存：直接换成新 key 的数据。
      // 新 key **没**缓存时不动 data，只把 loading 置回去——那时页面渲染的是
      // 骨架屏而不是旧数据（各页面的 loading 分支就是这么写的），旧内容不会露出来。
      setData(cached)
    }
    // 缓存命中时这一句是 no-op（初值已经是 false、数据已经是同一份），
    // 所以不会多渲染一次。
    setLoading(cached === undefined)
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

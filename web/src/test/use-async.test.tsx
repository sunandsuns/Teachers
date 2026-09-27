import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useAsync } from '../hooks/useAsync'

/**
 * `useAsync` 的缓存快照（第三个参数）。
 *
 * 这里要钉住的核心是一条**否定式**的断言：缓存命中时，**一帧 loading 都不许出现**。
 * 它比"首帧 data 有值"更强——因为"先置 loading、再在 effect 里改回来"照样能让
 * 首帧之后的数据是对的，但那一帧骨架屏已经画到屏幕上了，用户看到的就是白闪。
 * 所以下面用"每次渲染记一笔"的方式看**整条渲染序列**，而不是只看末态。
 */

/** 手动控制 resolve 时机的 loader，用来观察"数据还没回来"时的状态。 */
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(res => {
    resolve = res
  })
  return { promise, resolve }
}

describe('缓存命中：首帧直接出数据', () => {
  it('首帧就是数据，loading 为 false', () => {
    const cached = { tag: 'cached' }
    const pending = deferred<typeof cached>()

    const { result } = renderHook(() => useAsync(() => pending.promise, [], () => cached))

    expect(result.current.data).toBe(cached)
    expect(result.current.loading).toBe(false)
  })

  it('整条渲染序列里一次 loading 都没有', async () => {
    const cached = { tag: 'cached' }
    const seen: boolean[] = []
    const loader = vi.fn(async () => cached)

    renderHook(() => {
      const state = useAsync(loader, [], () => cached)
      seen.push(state.loading)
      return state
    })

    await waitFor(() => expect(loader).toHaveBeenCalled())
    // 只渲染过一次，且那一次的 loading 是 false。
    // "先 true 再 false"在这里会变成 [true, false]，测试当场变红。
    expect(seen).toEqual([false])
  })

  it('缓存只是起点，loader 回来之后以它为准', async () => {
    // 这条防的是"把 peek 当成"有缓存就别请求了""——那样数据会一直是旧的。
    const cached = { tag: 'stale' }
    const fresh = { tag: 'fresh' }

    const { result } = renderHook(() => useAsync(async () => fresh, [], () => cached))

    expect(result.current.data).toBe(cached)
    await waitFor(() => expect(result.current.data).toBe(fresh))
  })
})

describe('缓存未命中：照旧走 loading', () => {
  it('peek 返回 undefined 时先显示 loading', () => {
    const pending = deferred<{ tag: string }>()

    const { result } = renderHook(() => useAsync(() => pending.promise, [], () => undefined))

    expect(result.current.data).toBeNull()
    expect(result.current.loading).toBe(true)
  })

  it('没传 peek 时行为与从前完全一样', async () => {
    const payload = { tag: 'ok' }

    const { result } = renderHook(() => useAsync(async () => payload))

    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.data).toBe(payload))
    expect(result.current.loading).toBe(false)
  })

  it('peek 命中的是 null 也算命中——不该被当成"没有"', () => {
    // `null` 与 `undefined` 在这里是不同的意思：前者是"查到了，值是空"。
    // useAsync 只把 `undefined` 当作"手上没有"。
    const { result } = renderHook(() => useAsync(async () => null, [], () => null))
    expect(result.current.loading).toBe(false)
  })
})

describe('依赖变化：按新 key 找缓存', () => {
  it('新 key 有缓存时直接换过去，不回 loading', async () => {
    const forA = { tag: 'A' }
    const forB = { tag: 'B' }
    const cache: Record<string, { tag: string } | undefined> = { a: forA, b: forB }
    const loader = vi.fn(async () => ({ tag: 'network' }))

    const { result, rerender } = renderHook(
      ({ key }: { key: string }) => useAsync(loader, [key], () => cache[key]),
      { initialProps: { key: 'a' } },
    )
    expect(result.current.data).toBe(forA)

    rerender({ key: 'b' })
    expect(result.current.data).toBe(forB)
    expect(result.current.loading).toBe(false)
    // 等 rerender 触发的那次请求落定——否则它会在用例结束之后才 setState，
    // 报一个与本意无关的 act 警告。
    await waitFor(() => expect(result.current.data).toEqual({ tag: 'network' }))
  })

  it('新 key 没有缓存时回到 loading——不能把上一条的内容留在屏上', () => {
    const forA = { tag: 'A' }
    const pending = deferred<{ tag: string }>()
    const loader = vi.fn(() => pending.promise)

    const { result, rerender } = renderHook(
      ({ key }: { key: string }) => useAsync(loader, [key], () => (key === 'a' ? forA : undefined)),
      { initialProps: { key: 'a' } },
    )
    expect(result.current.data).toBe(forA)

    rerender({ key: 'b' })
    expect(result.current.loading).toBe(true)
  })
})

describe('reload：忽略缓存快照', () => {
  it('刷新会真去请求，而不是原样返回缓存', async () => {
    const cached = { tag: 'cached' }
    const loader = vi.fn(async () => ({ tag: 'fresh' }))

    const { result } = renderHook(() => useAsync(loader, [], () => cached))
    expect(result.current.data).toBe(cached)
    expect(loader).toHaveBeenCalledTimes(1)

    await act(async () => {
      result.current.reload()
    })

    await waitFor(() => expect(loader).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(result.current.data).toEqual({ tag: 'fresh' }))
  })

  it('强制标记是一次性的：刷新之后再换依赖，缓存照样生效', async () => {
    // 标记留成常驻的话，往后每次依赖变化都会绕过缓存，切页白闪又会回来——
    // 而且看不出是谁干的。
    const cached = { tag: 'cached' }
    const loader = vi.fn(async () => ({ tag: 'fresh' }))

    const { result, rerender } = renderHook(
      ({ key }: { key: string }) => useAsync(loader, [key], () => cached),
      { initialProps: { key: 'a' } },
    )

    await act(async () => {
      result.current.reload()
    })
    await waitFor(() => expect(loader).toHaveBeenCalledTimes(2))

    rerender({ key: 'b' })
    // 又命中缓存 → 不出现 loading。标记若残留，这里会变回 true。
    expect(result.current.loading).toBe(false)
    await waitFor(() => expect(result.current.data).toEqual({ tag: 'fresh' }))
  })
})

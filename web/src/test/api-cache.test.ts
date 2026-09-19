/** GET 缓存的行为契约。
 *
 * 缓存最怕的不是"没生效"，而是**该走网络的被缓存住了**：
 * 求教被缓存 = 用户拿到上一次的答案；写操作后不清 = 看到删掉的东西还在。
 * 所以这组用例的重点在边界，不在"命中率"。
 *
 * 另一个必须钉住的性质：**缓存只按路径生效**，不跨用例残留——
 * 模块级 Map 在同一个测试文件里是共享的，用例之间要能互不干扰。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api, clearApiCache } from '../api/client'

/** 造一个能数调用次数的 fetch 替身。 */
function stubFetch(payload: unknown = { ok: true }) {
  const calls: string[] = []
  const fake = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push(`${(init?.method ?? 'GET').toUpperCase()} ${url}`)
    return {
      ok: true,
      status: 200,
      json: async () => payload,
    } as unknown as Response
  })
  vi.stubGlobal('fetch', fake)
  return calls
}

beforeEach(() => {
  clearApiCache()
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearApiCache()
})

describe('GET 缓存', () => {
  it('同一路径第二次读走缓存，不再发请求', async () => {
    const calls = stubFetch([{ book_id: '01' }])
    await api.listBooks()
    await api.listBooks()
    expect(calls).toHaveLength(1)
  })

  it('书目数据只请求一次——但每次拿到的是同一份内容', async () => {
    stubFetch([{ book_id: '01', title: '易经' }])
    const first = await api.listBooks()
    const second = await api.listBooks()
    expect(first).toEqual(second)
  })

  it('并发读同一路径只发一次请求（切页很快时的常见情形）', async () => {
    const calls = stubFetch([{ book_id: '01' }])
    await Promise.all([api.listBooks(), api.listBooks(), api.listBooks()])
    expect(calls).toHaveLength(1)
  })

  it('不同路径各有各的缓存', async () => {
    const calls = stubFetch({})
    await api.listBooks()
    await api.kbGraph()
    await api.listBooks()
    await api.kbGraph()
    expect(calls).toHaveLength(2)
  })

  it('带参数的路径按整串区分：01 与 02 不会串', async () => {
    const calls = stubFetch({ book_id: '01' })
    await api.getBook('01')
    await api.getBook('02')
    await api.getBook('01')
    expect(calls).toEqual(['GET /api/books/01', 'GET /api/books/02'])
  })
})

describe('不该被缓存的东西', () => {
  it('求教每次都真发请求——缓存住等于给用户上一次的答案', async () => {
    const calls = stubFetch({ answer: 'x', conversation_id: 't' })
    await api.ask('我最近很焦虑')
    await api.ask('我最近很焦虑')
    expect(calls).toHaveLength(2)
  })

  it('「随机一条感悟」每次都要新的', async () => {
    const calls = stubFetch({ id: 1 })
    await api.randomInsight()
    await api.randomInsight()
    expect(calls).toHaveLength(2)
  })

  it('历史记录不缓存——刚问的那句必须立刻出现在「回响」里', async () => {
    const calls = stubFetch({ records: [] })
    await api.listTopics()
    await api.listTopics()
    expect(calls).toHaveLength(2)
  })

  it('探活自定义端点不缓存——用户改完 Key 再点一次就该重试', async () => {
    const calls = stubFetch({ ok: true, models: [] })
    const ep = { base_url: 'https://x/v1', api_key: 'k', model: '' }
    await api.probeModel(ep)
    await api.probeModel(ep)
    expect(calls).toHaveLength(2)
  })
})

describe('写操作让读缓存作废', () => {
  it('删掉一条特征后再读画像，看到的是新数据', async () => {
    const calls = stubFetch({ traits: [] })
    await api.getProfile()
    await api.deleteTrait(1)
    await api.getProfile()
    expect(calls).toEqual([
      'GET /api/profile',
      'DELETE /api/profile/traits/1',
      'GET /api/profile',
    ])
  })

  it('切性别之后重读画像（性别同时是人物筛选池）', async () => {
    const calls = stubFetch({ avatar: 'male' })
    await api.getProfile()
    await api.setAvatar('male')
    await api.getProfile()
    expect(calls.filter(c => c.startsWith('GET'))).toHaveLength(2)
  })

  it('清空画像之后，知识库与画像都重新读', async () => {
    const calls = stubFetch({})
    await api.getProfile()
    await api.kbGraph()
    await api.clearProfile()
    await api.getProfile()
    await api.kbGraph()
    expect(calls.filter(c => c.startsWith('GET'))).toHaveLength(4)
  })

  it('写操作失败时缓存保持有效（没改成，就不该让缓存失效）', async () => {
    let n = 0
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
      n += 1
      // 第一次 GET 成功；随后的 DELETE 失败
      if ((init?.method ?? 'GET').toUpperCase() === 'DELETE') {
        return { ok: false, status: 500, json: async () => ({}) } as unknown as Response
      }
      return { ok: true, status: 200, json: async () => ({ traits: [] }) } as unknown as Response
    }))

    await api.getProfile()
    await expect(api.deleteTrait(1)).rejects.toThrow()
    await api.getProfile()
    // GET 只发了一次：DELETE 失败没有把缓存清掉
    const gets = (globalThis.fetch as any).mock.calls.filter(
      (c: any[]) => ((c[1] as RequestInit | undefined)?.method ?? 'GET').toUpperCase() === 'GET',
    )
    expect(gets).toHaveLength(1)
  })
})

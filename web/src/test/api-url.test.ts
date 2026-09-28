/** 请求 URL 怎么拼——重点是**搜索词里的特殊字符**。
 *
 * 后台用户列表的搜索走 `GET /api/admin/users?q=`。`admin.test.tsx` 把整个 `api`
 * 换成了假的，所以"真正拼这一串 URL 的那几行"从来没被测过：把
 * `encodeURIComponent` 删掉，所有前端用例照样全绿，而界面上搜 `a&b` 会**静默**
 * 变成搜 `a`（`&b` 被当成第二个查询参数，后端认不出它，直接丢掉）——用户看到
 * 的结果比自己以为的多，而屏幕上没有任何地方提示"你的搜索词被改过"。
 *
 * 另一条同样静默的：`q` 为空时**不该**带上 `?q=`。带上之后请求串变了，
 * GET 缓存会多出一份"看起来是另一种请求、其实一模一样"的键。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api, clearApiCache } from '../api/client'

/** 造一个只记 URL 的 fetch 替身（与 `api-cache.test.ts` 同一套路子）。 */
function stubFetch(payload: unknown = []) {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push(`${(init?.method ?? 'GET').toUpperCase()} ${url}`)
    return { ok: true, status: 200, json: async () => payload } as unknown as Response
  }))
  return calls
}

beforeEach(() => {
  clearApiCache()
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearApiCache()
})

describe('后台用户列表的搜索词怎么进 URL', () => {
  it('不搜索时不带 `?q=`——与从前逐字相同的那一支请求', async () => {
    const calls = stubFetch()
    await api.adminUsers()
    expect(calls).toEqual(['GET /api/admin/users'])
  })

  it('只有空白也算没搜索（搜索框里敲几个空格不该变成一次"模糊匹配全部"）', async () => {
    const calls = stubFetch()
    await api.adminUsers('   ')
    expect(calls).toEqual(['GET /api/admin/users'])
  })

  it('普通搜索词原样带上', async () => {
    const calls = stubFetch()
    await api.adminUsers('bob@example.com')
    expect(calls).toEqual(['GET /api/admin/users?q=bob%40example.com'])
  })

  it('`&` 与 `=` 被编码——否则 `&b` 会变成一个后端不认识的查询参数', async () => {
    const calls = stubFetch()
    await api.adminUsers('a&b=c')
    expect(calls).toEqual(['GET /api/admin/users?q=a%26b%3Dc'])
    // 这条要是红了，先看上面那串里有没有裸露的 `&`：有就是"搜索词被截断"。
    expect(calls[0].split('&').length - 1).toBe(0)
  })

  it('中文昵称被编码', async () => {
    const calls = stubFetch()
    await api.adminUsers('张三')
    expect(calls).toEqual(['GET /api/admin/users?q=%E5%BC%A0%E4%B8%89'])
  })

  it('两头空白先去掉再编码（手滑多敲一个空格不等于搜不到人）', async () => {
    const calls = stubFetch()
    await api.adminUsers('  张三  ')
    expect(calls).toEqual(['GET /api/admin/users?q=%E5%BC%A0%E4%B8%89'])
  })

  it('# 与 ? 也编码——它们会截断路径或另起一段查询', async () => {
    const calls = stubFetch()
    await api.adminUsers('a#b?c')
    expect(calls).toEqual(['GET /api/admin/users?q=a%23b%3Fc'])
  })
})

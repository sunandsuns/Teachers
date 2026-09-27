/**
 * OpenLibrary 的**浏览器直连**实现。
 *
 * 为什么会有这一份
 * --------------------------------------------------------------------------
 * 部署容器（在线版）跑在境内、且没有出海代理：到 `openlibrary.org` 的 TLS
 * 会被直接掐断（`TLS/SSL connection has been closed (EOF)`），后端那条路走不通。
 * 而**浏览器**那条路是通的——浏览器用的是访客自己的网络。OpenLibrary 的接口
 * 带 `Access-Control-Allow-Origin: *`（实测 `search.json` 与 `works/*.json`
 * 都是），可以从页面里直接取；封面图本来也一直是浏览器直连加载的。
 *
 * 所以「联网检索」的顺序是：**先走后端**（桌面版的后端就在本机，能连上，
 * 保底可用），后端回 `unavailable`（"没走到上游"）时才落到这里。判定见
 * `BookFinder`。
 *
 * 字段与去重规则与后端 `server/services/book_search.py` 一字对应：换条路不该
 * 换来换去换出两套结果。
 */

import type { BookCandidate } from './client'

const SEARCH_URL = 'https://openlibrary.org/search.json'
const WORKS_URL = 'https://openlibrary.org/works'
const COVER_URL = 'https://covers.openlibrary.org/b/id'

/** 与后端 `book_search.SEARCH_FIELDS` 同一批字段：默认返回体里有几十个用不上的。 */
const SEARCH_FIELDS = 'title,author_name,first_publish_year,cover_i,key,subject'

/** 主题最多留几个（与后端 `MAX_SUBJECTS` 一致）。 */
const MAX_SUBJECTS = 8

/** 简介截断长度（与后端 `MAX_SUMMARY` 一致）。 */
const MAX_SUMMARY = 1200

/** 检索超时。比后端那 12s 稍短一点：用户是在等一个列表。 */
const TIMEOUT_MS = 10000

/** 直连这条路走不通（网络、CORS、超时）。消息是给用户看的中文。 */
export class BookSearchUnavailable extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'BookSearchUnavailable'
  }
}

async function getJson(url: string): Promise<unknown> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    // Accept 属于 CORS 安全列表头，不会额外触发 preflight。
    const response = await fetch(url, { signal: controller.signal, headers: { Accept: 'application/json' } })
    if (!response.ok) {
      throw new BookSearchUnavailable(`检索服务返回 HTTP ${response.status}`)
    }
    return await response.json()
  } catch (err) {
    if (err instanceof BookSearchUnavailable) throw err
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new BookSearchUnavailable('浏览器直连检索服务超时')
    }
    throw new BookSearchUnavailable(`无法从浏览器连接检索服务：${err instanceof Error ? err.message : String(err)}`)
  } finally {
    clearTimeout(timer)
  }
}

function text(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value).trim()
}

/** 把 OpenLibrary 的一条 doc 转成候选；没有书名就丢掉。 */
function toCandidate(doc: Record<string, unknown>): BookCandidate | null {
  const title = text(doc.title)
  if (!title) return null

  const rawAuthors = doc.author_name
  const author = Array.isArray(rawAuthors)
    ? rawAuthors
        .slice(0, 2)
        .map(text)
        .filter(Boolean)
        .join('、')
    : text(rawAuthors)

  // "/works/OL27448W" → "OL27448W"
  const rawKey = text(doc.key)
  const sourceKey = rawKey ? (rawKey.split('/').pop() ?? '') : ''

  const cover = doc.cover_i
  let coverUrl = ''
  if (typeof cover === 'number' && cover > 0) coverUrl = `${COVER_URL}/${cover}-M.jpg`
  else if (typeof cover === 'string' && /^\d+$/.test(cover)) coverUrl = `${COVER_URL}/${Number(cover)}-M.jpg`

  const rawSubjects = doc.subject
  const subjects = Array.isArray(rawSubjects)
    ? rawSubjects.slice(0, MAX_SUBJECTS).map(text).filter(Boolean)
    : []

  return {
    title,
    author,
    year: text(doc.first_publish_year),
    cover_url: coverUrl,
    source_key: sourceKey,
    source: 'openlibrary',
    summary: '',
    subjects,
  }
}

async function query(params: URLSearchParams, limit: number): Promise<BookCandidate[]> {
  const data = (await getJson(`${SEARCH_URL}?${params.toString()}`)) as { docs?: unknown }
  const docs = data?.docs
  if (!Array.isArray(docs)) throw new BookSearchUnavailable('检索结果格式异常')

  const results: BookCandidate[] = []
  const seen = new Set<string>()
  for (const doc of docs) {
    if (!doc || typeof doc !== 'object') continue
    const candidate = toCandidate(doc as Record<string, unknown>)
    if (!candidate) continue
    // 同一本书的不同版本（精装/平装/再版）各占一条、work id 相同，按它去重
    if (candidate.source_key && seen.has(candidate.source_key)) continue
    if (candidate.source_key) seen.add(candidate.source_key)
    results.push(candidate)
    if (results.length >= limit) break
  }
  return results
}

/**
 * 按书名 / 作者检索。
 *
 * 书名与作者同时给出却一条都没命中时，**退化为只用书名再搜一次**——与后端同一
 * 套逻辑：OpenLibrary 的作者名格式很杂，拿它做 AND 过滤容易把本该命中的筛掉。
 */
export async function searchBooksDirect(title: string, author = '', limit = 6): Promise<BookCandidate[]> {
  const cleanTitle = (title || '').trim()
  const cleanAuthor = (author || '').trim()

  const params = new URLSearchParams({ limit: String(limit), fields: SEARCH_FIELDS })
  if (cleanTitle) params.set('title', cleanTitle)
  if (cleanAuthor) params.set('author', cleanAuthor)

  const results = await query(params, limit)
  if (results.length > 0 || !(cleanTitle && cleanAuthor)) return results

  const retry = new URLSearchParams({ limit: String(limit), fields: SEARCH_FIELDS, title: cleanTitle })
  return query(retry, limit)
}

/** 简介可能是纯字符串，也可能是 `{type, value}`。与后端 `_describe` 一致。 */
function describe(raw: unknown): string {
  let value = ''
  if (typeof raw === 'string') value = raw.trim()
  else if (raw && typeof raw === 'object') value = text((raw as Record<string, unknown>).value)

  if (value.length > MAX_SUMMARY) {
    let cut = value.slice(0, MAX_SUMMARY)
    for (const mark of ['。', '\n', '. ']) {
      const index = cut.lastIndexOf(mark)
      if (index > MAX_SUMMARY / 2) {
        cut = cut.slice(0, index + mark.length)
        break
      }
    }
    value = `${cut.trimEnd()}…`
  }
  return value
}

/**
 * 取一本书的详情（简介 + 主题），用于**加进书架之前**补上简介。
 *
 * 后端在 `POST /shelf/books` 里自己会补一次；但在线版的后端补不到（同一个
 * 网络原因），所以由浏览器把它带过去。失败返回 `null`——详情是锦上添花，
 * 拿不到也该能把书加进去。
 */
export async function fetchDetailDirect(sourceKey: string): Promise<Pick<BookCandidate, 'summary' | 'subjects'> | null> {
  const key = (sourceKey || '').trim()
  if (!key) return null
  const path = key.startsWith('/') ? key : `${WORKS_URL}/${key}`
  const url = path.startsWith('http') ? `${path}.json` : `https://openlibrary.org${path}.json`

  try {
    const data = (await getJson(url)) as Record<string, unknown> | null
    if (!data || typeof data !== 'object') return null
    const rawSubjects = data.subjects
    const subjects = Array.isArray(rawSubjects)
      ? rawSubjects.slice(0, MAX_SUBJECTS).map(text).filter(Boolean)
      : []
    return { summary: describe(data.description), subjects }
  } catch {
    return null
  }
}

/** 后端 API 客户端：唯一的网络访问层，页面组件不得直接 fetch。 */

const BASE = '/api'

export interface BookSummary {
  book_id: string
  title: string
  author: string
  category: string
  chapter_count: number
  has_source: boolean
}

export interface ChapterSummary {
  chapter_id: string
  title: string
  book_id: string
}

export interface ChapterDetail {
  chapter_id: string
  title: string
  book_id: string
  content: string
}

export type SearchKind = 'all' | 'notes' | 'source'

export interface SearchResultItem {
  book_id: string
  book_title: string
  chapter_id: string
  chapter_title: string
  content: string
  score: number
  source: string
  /** 来源类型：notes 深读笔记 / source 原典全文 */
  kind: 'notes' | 'source'
  /** kind 为 source 时，该段在原典全文中的字符位置 */
  offset: number
}

export interface SearchResponse {
  query: string
  total: number
  results: SearchResultItem[]
}

export interface SourceChunk {
  book_id: string
  title: string
  content: string
  offset: number
  limit: number
  total: number
  has_more: boolean
}

export interface AskResponse {
  question: string
  answer: string
  retrieved_count: number
  llm_used: boolean
  model: string | null
}

export interface AskStatus {
  enabled: boolean
  base_url: string
  model: string
  available_models: number
  cooling_down: string[]
  last_error: string
}

export interface InsightItem {
  id: number
  text: string
  interpretation: string
  source: string
  book_id: string
  themes: string[]
}

export interface ThemeListResponse {
  themes: string[]
  counts: Record<string, number>
}

export interface InsightListResponse {
  total: number
  items: InsightItem[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => null)
    const message = detail?.detail ?? `请求失败（${resp.status}）`
    throw new Error(message)
  }
  return resp.json() as Promise<T>
}

export const api = {
  listBooks: () => request<BookSummary[]>('/books'),

  getBook: (bookId: string) => request<BookSummary>(`/books/${bookId}`),

  listChapters: (bookId: string) =>
    request<ChapterSummary[]>(`/books/${bookId}/chapters`),

  getChapter: (bookId: string, chapterId: string) =>
    request<ChapterDetail>(`/books/${bookId}/chapters/${chapterId}`),

  /** 原典分块：大书（如《资治通鉴》310 万字）需按 has_more 逐块取 */
  getSource: (bookId: string, offset = 0) =>
    request<SourceChunk>(`/books/${bookId}/source?offset=${offset}`),

  search: (q: string, topK = 5, kind: SearchKind = 'all') =>
    request<SearchResponse>(
      `/search?q=${encodeURIComponent(q)}&top_k=${topK}&kind=${kind}`,
    ),

  ask: (question: string, topK = 5) =>
    request<AskResponse>('/ask', {
      method: 'POST',
      body: JSON.stringify({ question, top_k: topK }),
    }),

  askStatus: () => request<AskStatus>('/ask/status'),

  dailyInsight: (day?: string) =>
    request<InsightItem>(`/insight/daily${day ? `?day=${day}` : ''}`),

  randomInsight: () => request<InsightItem>('/insight/random'),

  insightThemes: () => request<ThemeListResponse>('/insight/themes'),

  insightsByTheme: (theme: string) =>
    request<InsightListResponse>(`/insight/by-theme/${encodeURIComponent(theme)}`),

  insightsByBook: (bookId: string) =>
    request<InsightListResponse>(`/insight/by-book/${bookId}`),
}

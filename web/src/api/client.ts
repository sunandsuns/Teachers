/** 后端 API 客户端：唯一的网络访问层，页面组件不得直接 fetch。
 *
 * 数据形状在 `types.ts`，这里只管怎么发请求。
 */

import type {
  AskResponse,
  AskStatus,
  BookSummary,
  ChapterDetail,
  ChapterSummary,
  DeleteResult,
  HistoryListResponse,
  HistoryStatus,
  InsightItem,
  InsightListResponse,
  LLMEndpoint,
  ProbeResult,
  SearchKind,
  SearchResponse,
  SourceChunk,
  ThemeListResponse,
} from './types'

// 类型从这里一并转出，调用方只认 '../api/client' 这一个入口
export * from './types'

const BASE = '/api'

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

  /** 求教。`llm` 省略时用后端内置的默认模型，见 `useModelSettings`。 */
  ask: (question: string, topK = 5, llm?: LLMEndpoint | null) =>
    request<AskResponse>('/ask', {
      method: 'POST',
      body: JSON.stringify({ question, top_k: topK, ...(llm ? { llm } : {}) }),
    }),

  /** 测一个自定义端点通不通。Key 只在这一次请求里传递，后端不留存。 */
  probeModel: (llm: LLMEndpoint) =>
    request<ProbeResult>('/ask/probe', {
      method: 'POST',
      body: JSON.stringify(llm),
    }),

  askStatus: () => request<AskStatus>('/ask/status'),

  // 「回响」——求教历史的读写。记录由后端在每次求教时自动存入。
  listHistory: (limit = 20, offset = 0) =>
    request<HistoryListResponse>(`/history?limit=${limit}&offset=${offset}`),

  /** 存储概况。打开页面时调它，后端顺带做一次机会式清理。 */
  historyStatus: () => request<HistoryStatus>('/history/status'),

  deleteHistory: (id: number) =>
    request<DeleteResult>(`/history/${id}`, { method: 'DELETE' }),

  clearHistory: () => request<DeleteResult>('/history', { method: 'DELETE' }),

  dailyInsight: (day?: string) =>
    request<InsightItem>(`/insight/daily${day ? `?day=${day}` : ''}`),

  randomInsight: () => request<InsightItem>('/insight/random'),

  insightThemes: () => request<ThemeListResponse>('/insight/themes'),

  insightsByTheme: (theme: string) =>
    request<InsightListResponse>(`/insight/by-theme/${encodeURIComponent(theme)}`),

  insightsByBook: (bookId: string) =>
    request<InsightListResponse>(`/insight/by-book/${bookId}`),
}

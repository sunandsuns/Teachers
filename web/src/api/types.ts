/** 后端接口的数据形状。
 *
 * 与 `client.ts` 拆开：请求逻辑会把文件越写越长，而类型是纯声明、
 * 阅读时不需要跟 `fetch` 细节混在一起。这里只放类型，不放任何运行时代码。
 */

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

/**
 * 自定义模型端点。三个字段全空即"用内置的默认模型"；
 * 只填一半（有地址没 Key）后端会视同全空，按默认走。
 */
export interface LLMEndpoint {
  base_url: string
  api_key: string
  /** 留空则由后端自动挑选可用模型 */
  model: string
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

/** 「测试连接」的结果。失败时 error 里是给人看的原因。 */
export interface ProbeResult {
  ok: boolean
  base_url: string
  model: string
  models: string[]
  error: string
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

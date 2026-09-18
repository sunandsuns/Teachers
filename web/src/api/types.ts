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

/** 一轮旧问答。追问时随请求带上，模型才知道"刚才聊到哪"。 */
export interface ChatTurn {
  question: string
  answer: string
}

export interface AskResponse {
  question: string
  answer: string
  retrieved_count: number
  llm_used: boolean
  model: string | null
  /** 这次问答在「回响」里的编号；没能记上（数据库不可用）时为 null */
  history_id: number | null
  /** 这次问答所属的话题；追问时原样带回，好归到同一张卡片下 */
  conversation_id: string
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

/** 一条求教记录（「回响」）。 */
export interface HistoryItem {
  id: number
  question: string
  answer: string
  /** 产出回答的模型；null 表示这次是本地检索降级 */
  model: string | null
  llm_used: boolean
  retrieved_count: number
  /** 所属话题；升级前的老记录为 null */
  conversation_id: string | null
  /** 本地时区的 ISO 8601 */
  created_at: string
  created_ts: number
}

/** 一个话题：一次会话里的连续追问聚成的一张卡片。 */
export interface TopicItem {
  /** 话题 id；升级前的老记录是 `solo:<记录id>` */
  id: string
  /** 话题的第一问，充当标题 */
  title: string
  question_count: number
  first_ts: number
  last_ts: number
  latest_question: string
  latest_answer: string
}

export interface TopicListResponse {
  available: boolean
  error: string
  /** 话题数，不是记录数 */
  total: number
  items: TopicItem[]
}

/**
 * 记录列表。`available` 为 false 时列表必为空、`error` 里是原因——
 * 数据库建不出来（程序目录只读、磁盘满）不算请求失败。
 */
export interface HistoryListResponse {
  available: boolean
  error: string
  total: number
  items: HistoryItem[]
}

/** 历史记录存储的概况。 */
export interface HistoryStatus {
  available: boolean
  error: string
  db_path: string
  total: number
  /** 保留天数。默认半个月 */
  retention_days: number
  last_purge_at: string | null
  /** 下一次自动清理的时间 */
  next_purge_at: string | null
  size_bytes: number
}

/** 删除结果。 */
export interface DeleteResult {
  deleted: number
}

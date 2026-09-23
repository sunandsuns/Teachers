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

/** 一条对话消息（后端组装好，交给浏览器去调云模型）。 */
export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

/**
 * 「只检索、不生成」的结果。
 *
 * 走云模型时用：后端把材料与提示词准备好，生成发生在浏览器里
 * （原因见 `lib/cloud.ts`）。生成完再调 `saveAsk` 补记进「回响」。
 */
export interface AskPlan {
  question: string
  messages: ChatMessage[]
  lang: string
  retrieved_count: number
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

/**
 * 勾选删除的目标：记录 id 与话题 id 可以混着给，也可以只给一边。
 *
 * 后端把两串条件并起来删（`WHERE id IN (...) OR conversation_id = ...`），
 * 所以一次请求就能删掉"几条单独问答 + 几段完整对话"的混合选择。
 */
export interface DeleteTargets {
  /** 要删的记录 id */
  ids?: number[]
  /** 要整段删掉的话题 id（含老记录的 `solo:<记录id>`） */
  topics?: string[]
}

/** 一条画像特征。 */
export interface TraitItem {
  id: number
  /** 分类：性格 / 年龄 / 爱好 / 生活条件 / 成熟度 / 专业 / 规划。
   *  后端的封闭集合，界面把它译成标签，**不要**当成自由文本处理。 */
  category: string
  content: string
  /** 依据：用户自己说过的哪句话让模型这么判断 */
  evidence: string
  /** 模型的把握程度，0~1 */
  confidence: number
}

/** 形象性别。 */
export type Avatar = 'male' | 'female'

/** 「最像你的一位历史人物」。
 *
 *  整块都可能是空的（还没评过、名录里没人、库不可用）：那时 `id` 是空串，
 *  界面退回默认的两页册页。名字、时代、署名每次都从后端的名录现取，所以
 *  改了名录立刻生效——**不要**把它缓存成"选中那一刻的样子"。 */
export interface FigureInfo {
  id: string
  name: string
  era: string
  /** 一句话说他是谁 */
  blurb: string
  /** 模型写的：像在哪里。名单里挑的是这个人的哪些点 */
  reason: string
  /** 题签式的署名：这一幅画出在哪本书、哪本册子，或谁拍的 */
  credit: string
  /** 画像的相对 URL，可直接放进 <img src> */
  portrait: string
  /** 评出时的 ISO 周，如 2026-W38 */
  week: string
  /** 评出的日期，YYYY-MM-DD */
  chosen_at: string
  /** 该性别名录里共有多少位候选 */
  pool_size: number
  /** 现在该不该重新评定一次。为真时页面在后台补一次，不打扰用户 */
  needs_refresh: boolean
}

/** 一次历史人物评定的结果。`error` 是机器可读的代号，或上游给的错误文本。 */
export interface FigureResult {
  ok: boolean
  id: string
  llm_used: boolean
  error: string
}

/** 画像全貌。`available` 为 false 时 `traits` 必为空、`error` 里是原因。 */
export interface ProfileResponse {
  available: boolean
  error: string
  avatar: Avatar
  total: number
  traits: TraitItem[]
  /** 全部分类，界面按它排引线 */
  categories: string[]
  /** 上次归纳之后又问了多少条。大于 0 就值得再归纳一次 */
  pending: number
  /** 最像你的一位历史人物 */
  figure: FigureInfo
}

/** 一次归纳的结果。`error` 是机器可读的代号，或上游给的错误文本。 */
export interface ExtractResult {
  ok: boolean
  /** 本次新增或更新的条数 */
  extracted: number
  /** 画像里现在共有几条 */
  total: number
  llm_used: boolean
  error: string
}

// ── 知识库 ──────────────────────────────────────────────────────────────
// 节点 ID 是带类型前缀的字符串（`book:08` / `theme:逆境` / `chapter:08:04`），
// 前端不需要另一张对照表就能判断它是什么。

export type KbNodeKind = 'book' | 'theme' | 'chapter'

/** 边类型：主题归属 / 经典互参 / 章节构成 */
export type KbEdgeKind = 'theme' | 'cross' | 'part'

/** 节点上的附属信息。**按 kind 取用**：书的字段与主题的字段不重叠。 */
export interface KbNodeMeta {
  book_id?: string
  book_title?: string
  chapter_id?: string
  theme?: string
  author?: string
  category?: string
  chapter_count?: number
  has_source?: boolean
}

export interface KbNode {
  id: string
  kind: KbNodeKind
  label: string
  /** 关联边数。界面据它决定节点大小 */
  degree: number
  meta: KbNodeMeta
}

export interface KbEdge {
  source: string
  target: string
  kind: KbEdgeKind
  /** 边上的说明。空串表示"关系成立但没留下说明" */
  label: string
  weight: number
}

export interface KbGraph {
  nodes: KbNode[]
  edges: KbEdge[]
  stats: Record<string, unknown>
}

/** 一条双链。`direction` 为 out 时 `node_id` 是目标，in 时是来源。 */
export interface KbLink {
  node_id: string
  label: string
  kind: KbEdgeKind
  edge_label: string
  direction: 'out' | 'in'
}

/** 某书在某主题下的判断与代表章句。 */
export interface KbThemeRow {
  theme: string
  book_id: string
  book_title: string
  judgment: string
  quote: string
}

/** 笔记里写下的一句互参原文。 */
export interface KbCrossRef {
  name: string
  detail: string
}

export interface KbNodeDetail {
  node: KbNode
  outgoing: KbLink[]
  backlinks: KbLink[]
  theme_rows: KbThemeRow[]
  cross_refs: KbCrossRef[]
}

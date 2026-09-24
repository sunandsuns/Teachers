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

export type SearchKind = 'all' | 'notes' | 'source' | 'shelf'

/** 检索结果的来源类型。 */
export type SearchResultKind = 'notes' | 'source' | 'shelf'

export interface SearchResultItem {
  book_id: string
  book_title: string
  chapter_id: string
  chapter_title: string
  content: string
  score: number
  source: string
  /** 来源类型：notes 深读笔记 / source 原典全文 / shelf 我自己的书架 */
  kind: SearchResultKind
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

// ── 账号 ────────────────────────────────────────────────────────────────
//
// 「未登录」是一个**正常状态**，不是错误：整套检索、阅读、求教都对匿名开放。
// 所以 `me` 返回的是 `{ user: null }` 而不是 401，前端也就不必为它写一层
// 错误处理——只有真正的失败才会走到 catch。

/** 当前登录的用户。**不含密码哈希与 salt**，后端从不外发那两个字段。 */
export interface UserInfo {
  id: number
  /** 邮箱，同时是登录账号 */
  email: string
  /** 昵称；注册时留空则为空串 */
  display_name: string
  /** 界面上优先显示的名字：有昵称用昵称，没有就用邮箱 @ 之前那一段 */
  name: string
  is_admin: boolean
  created_at: string
}

/** `GET /api/auth/me` 的响应。未登录时 `user` 为 null。 */
export interface MeResponse {
  user: UserInfo | null
}

// ── 个人书架 ────────────────────────────────────────────────────────────

/** 阅读状态。与后端 `user_books.STATUSES` 一一对应。 */
export type ShelfStatus = 'wish' | 'reading' | 'done'

/**
 * 可见性。
 *
 * - `private`  只有自己看得见
 * - `pending`  已申请公开，在管理员的待审队列里
 * - `public`   已进公共书架，所有人检索得到
 * - `rejected` 管理员驳回；`review_note` 里是原因
 */
export type ShelfVisibility = 'private' | 'pending' | 'public' | 'rejected'

/**
 * 联网检索回来的一本书（候选）。
 *
 * 前端把用户选中的那条**原样回传**给加书接口，所以这个形状同时是入参。
 * `source_key` 是数据源里的稳定标识（OpenLibrary 的 work id），
 * 加书时靠它去补简介、也靠它去重。
 */
export interface BookCandidate {
  title: string
  author: string
  year: string
  cover_url: string
  source_key: string
  /** 数据源标识，目前只有 openlibrary */
  source: string
  summary: string
  subjects: string[]
}

/** 联网检索的结果。`error` 非空表示"这次没搜成"，给人看的原因。 */
export interface BookSearchResponse {
  results: BookCandidate[]
  error: string
}

/** 书架上的一本书。 */
export interface ShelfBook {
  id: number
  title: string
  author: string
  year: string
  cover_url: string
  source_key: string
  summary: string
  subjects: string[]
  /** 模型写的导读（Markdown）。加书是异步补的，刚加完可能还是空串 */
  guide: string
  /** 导读是否已生成。为 false 时前端值得过几秒再拉一次 */
  has_guide: boolean
  status: ShelfStatus
  visibility: ShelfVisibility
  /** 驳回原因，只有 `visibility === 'rejected'` 时有内容 */
  review_note: string
  created_at: string
  updated_at: string
}

/** 我的书架。`counts` 是各状态下的册数，外加一个 `total`。 */
export interface ShelfResponse {
  total: number
  counts: Record<string, number>
  books: ShelfBook[]
}

// ── 后台管理 ────────────────────────────────────────────────────────────

/**
 * 数据总览。
 *
 * 前半段是库层面的计数（用户、问答、书架、待审…），后半段是**语料规模**——
 * 后者由路由层从内容加载器补上，不是数据库里的东西。
 */
export interface AdminOverview {
  users: number
  admins: number
  history: number
  history_today: number
  traits: number
  shelf_books: number
  shelf_books_today: number
  pending_review: number
  public_contributions: number
  sessions: number
  db_bytes: number
  tables: number
  corpus_books: number
  corpus_chapters: number
  corpus_categories: string[]
  db_path: string
  server_time: string
}

/** 用户管理列表里的一行。 */
export interface AdminUserRow {
  id: number
  email: string
  name: string
  display_name: string
  is_admin: boolean
  created_at: string
  /** 这个人的藏书数 */
  shelf_books: number
}

/** 待审队列里的一行：用户申请公开的一本书。 */
export interface ReviewRow {
  /** 用户书架里那条记录的 id */
  id: number
  user_id: number
  user_email: string
  title: string
  author: string
  year: string
  cover_url: string
  summary: string
  subjects: string[]
  guide: string
  has_guide: boolean
  visibility: ShelfVisibility
  review_note: string
  created_at: string
}

/** 公共书架里由用户贡献的一本。 */
export interface PublicBookRow {
  id: number
  /** 公共书号，形如 `u01`——`u` 前缀把它与内置的 `01`…`15` 区分开 */
  book_id: string
  title: string
  author: string
  category: string
  from_user_id: number | null
  created_at: string
}

/** 数据库里的一张表。 */
export interface DbTable {
  name: string
  rows: number
}

/** 一列的结构。`protected` 为真表示不允许在这个界面直接改（如密码哈希）。 */
export interface DbColumn {
  name: string
  type: string
  notnull: boolean
  pk: boolean
  protected: boolean
}

/**
 * 一张表的结构与当前页数据。
 *
 * `rows` 里每行都带 `_rowid`——它是改/删时的定位依据。用 rowid 而不是主键，
 * 是因为有些表（如 `meta`）的主键是 TEXT，而 `public_books` 的 `book_id`
 * 与自增 id 也不是一回事。
 */
export interface DbTableData {
  table: string
  columns: DbColumn[]
  total: number
  rows: Record<string, unknown>[]
}

/** 一条后台操作痕迹。 */
export interface AuditEntry {
  id: number
  user_id: number | null
  action: string
  target: string
  detail: string
  created_at: string
}

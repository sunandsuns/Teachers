/**
 * 后端接口的数据形状。
 *
 * **本文件由 `python packaging/gen_web_types.py` 自动生成，不要手改。**
 * 要改接口就改 `server/schemas/`，然后重新生成（`npm run gen:api`）。
 *
 * 这里除了从 OpenAPI 直接来的模型，还有生成器补的两块（见生成脚本里的
 * `ENUMS` / `FIELD_TYPES` / `EXTRA_TYPES`）：后端把一些值域写在字段的
 * description 里、类型只写 `str`，前端要能穷尽检查，所以在契约层补上。
 *
 * 纯前端的概念（`SearchKind` 之类）不在这里，在 `./types`。
 */

export interface AddBookRequest {
  title: string
  author?: string
  year?: string
  cover_url?: string
  source_key?: string
  /** 数据源标识，目前只有 openlibrary */
  source?: string
  summary?: string
  subjects?: string[]
  /** wish / reading / done */
  status?: string
  /** 是否让模型生成导读 */
  with_guide?: boolean
}

/**
 * 数据总览。
 *
 * 前 12 个字段是库层面的统计（由 ``services/admin.py`` 出），后 5 个由路由层
 * 补上——语料规模是**内容层**的事，库不该知道。
 *
 * 这个接口先前在 OpenAPI 里是一个空对象：调用方无从知道后台到底统计了什么。
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

/** 检索结果与组装好的提示词。 */
export interface AskPlan {
  question: string
  messages: ChatMessage[]
  lang: string
  retrieved_count: number
  conversation_id: string
}

/** 只检索、不生成的请求。字段与 :class:`AskRequest` 保持一致，减去 ``llm``。 */
export interface AskPlanRequest {
  /** 用户问题 */
  question: string
  /** 检索结果数 */
  top_k?: number
  /** 作答语言：zh / en */
  lang?: string
  /** 话题 id；留空则新开一个 */
  conversation_id?: string
  history?: ChatTurn[]
}

/** 问答请求。 */
export interface AskRequest {
  /** 用户问题 */
  question: string
  /** 检索结果数 */
  top_k?: number
  /** 作答语言：zh / en；留空或无法识别时按 zh */
  lang?: string
  /** 话题 id：带上就是接着那个话题追问，留空则新开一个 */
  conversation_id?: string
  /** 最近几轮问答（新的在后）。追问时带上，回答才不会像失忆 */
  history?: ChatTurn[]
  /** 自定义模型端点；省略或留空则使用内置的默认模型 */
  llm: LLMEndpoint | null
}

/** 问答响应。 */
export interface AskResponse {
  question: string
  answer: string
  retrieved_count: number
  llm_used: boolean
  /** 实际使用的模型；未走 LLM 时为 null */
  model: string | null
  /** 这条问答在历史记录里的 id；未记上（库不可用等）为 null */
  history_id: number | null
  /** 这次问答所属的话题；追问时原样带回 */
  conversation_id: string
}

/** 浏览器侧生成完，把这一问一答送回来存档。 */
export interface AskSaveRequest {
  /** 用户问题 */
  question: string
  /** 模型生成的回答 */
  answer: string
  /** 实际使用的模型名；留空记为云端来源 */
  model?: string
  /** 这次用了几条检索片段 */
  retrieved_count?: number
  /** 话题 id；留空则新开一个 */
  conversation_id?: string
}

/** 问答能力状态（描述内置默认模型，不含用户自填的端点）。 */
export interface AskStatus {
  enabled: boolean
  base_url: string
  model: string
  available_models: number
  cooling_down: string[]
  last_error: string
}

/**
 * 一条后台操作痕迹。
 *
 * ``user_id`` 可以是 ``null``：那表示系统动作，不是某个人做的
 * （见 ``admin_audit`` 表的注释）。
 */
export interface AuditEntry {
  id: number
  user_id: number | null
  action: string
  target: string
  detail: string
  created_at: string
}

export type Avatar = 'male' | 'female'

/** 切换形象。 */
export interface AvatarRequest {
  /** male / female；认不出的值按默认 */
  gender?: string
}

export interface AvatarResponse {
  avatar: string
}

/** 一本书的元信息。前端把用户选中的候选原样回传。 */
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

/**
 * 找书的候选结果。
 *
 * 名字里带 ``Book`` 是为了与 ``search.SearchResponse``（全站检索）分开：
 * 两者曾同名，FastAPI 只好把其中一个导出成
 * ``server__schemas__shelf__SearchResponse``，对读接口文档的人是纯粹的噪音。
 */
export interface BookSearchResponse {
  results: BookCandidate[]
  error: string
}

/** 书目摘要（列表用）。 */
export interface BookSummary {
  book_id: string
  title: string
  author: string
  category: string
  chapter_count: number
  has_source: boolean
}

export interface ChangePasswordRequest {
  old_password: string
  new_password: string
}

/** 章节详情（阅读用）。 */
export interface ChapterDetail {
  chapter_id: string
  title: string
  book_id: string
  content: string
}

/** 章节摘要（列表用）。 */
export interface ChapterSummary {
  chapter_id: string
  title: string
  book_id: string
}

/** 一条对话消息。后端组装好交给浏览器去生成。 */
export interface ChatMessage {
  /** system / user / assistant */
  role: ChatMessageRole
  /** 消息正文 */
  content: string
}

export type ChatMessageRole = 'system' | 'user' | 'assistant'

/** 一轮旧问答。追问时随请求带上来，模型才知道刚才聊到哪。 */
export interface ChatTurn {
  /** 当时的提问 */
  question?: string
  /** 当时得到的回答 */
  answer?: string
}

/** 表的一列。``protected`` 为真时后台不允许改写它。 */
export interface DbColumn {
  name: string
  type: string
  notnull: boolean
  pk: boolean
  protected: boolean
}

/** 一张可操作的表。 */
export interface DbTable {
  name: string
  rows: number
}

/**
 * 一张表的结构与数据（分页）。
 *
 * ``rows`` 里是**任意列**——这是数据库浏览器，列随表变，没法也不该逐个建模。
 * 值可能是 ``null``（库里存的就是 NULL，与空串不是一回事）。
 */
export interface DbTableData {
  table: string
  columns: DbColumn[]
  total: number
  rows: Record<string, unknown>[]
}

/** 删除结果。``deleted`` 是实际删掉的条数——可能少于请求的条数。 */
export interface DeleteResult {
  deleted: number
}

/**
 * 勾选删除的目标：记录 id 与话题 id 可以混着给，也可以只给一边。
 *
 * 两个清单都设了长度上限：这是**不可撤销**的操作，与其收下一个畸形请求
 * （比如几万个 id）去拼一条巨型 SQL，不如当场返回 422。界面上的勾选量来自
 * 已加载的列表，远够不到这个数。
 */
export interface DeleteTargets {
  /** 要删的记录 id */
  ids?: number[]
  /** 要整段删掉的话题 id（含老记录的 solo:<记录id>） */
  topics?: string[]
}

/**
 * **所有**出错响应的形状。
 *
 * 这是契约里最该显眼的一条：调用方只需要写一次错误处理。
 *
 * ``code`` 给机器读：按它分支（比如 ``bad_credentials`` 时把光标放回密码框），
 * 而不是去比中文文案——文案会随语言变。
 * ``message`` 给人读：已经是可以直接展示的一句话。
 *
 * ``status`` 与 ``code`` 的对应由 ``server/errors.py`` 决定；这里只是形状。
 */
export interface ErrorBody {
  code: string
  message: string
}

/** 归纳请求。`lang` 决定特征正文用哪种语言写；分类始终是中文封闭集合。 */
export interface ExtractRequest {
  /** zh / en */
  lang?: string
}

/** 一次归纳的结果。``error`` 为机器可读的代号或上游错误文本。 */
export interface ExtractResult {
  ok: boolean
  /** 本次新增或更新的条数 */
  extracted: number
  /** 画像里现在共有几条 */
  total: number
  llm_used: boolean
  error: string
}

/**
 * 「最像你的一位历史人物」。
 *
 * 整块都可能为空（还没选出 / 名录为空 / 库不可用）：那时 ``id`` 是空串，
 * 界面退回默认的两页册页。
 */
export interface FigureInfo {
  id: string
  name: string
  era: string
  /** 一句话说他是谁 */
  blurb: string
  /** 模型写的：像在哪里 */
  reason: string
  /** 题签式的出处 */
  credit: string
  /** 画像的相对 URL，可直接放进 <img src> */
  portrait: string
  /** 选出时的 ISO 周，如 2026-W38 */
  week: string
  /** 选出的日期，YYYY-MM-DD */
  chosen_at: string
  /** 该性别下的候选人数 */
  pool_size: number
  /** 是否该重新评定一次。跨周且画像有变化、或还没评过、或选中的人已不在名录里，都为真。界面据此在后台补一次评定。 */
  needs_refresh: boolean
}

/** 一次历史人物评定的结果。``error`` 为机器可读的代号或上游错误文本。 */
export interface FigureResult {
  ok: boolean
  id: string
  llm_used: boolean
  error: string
}

/**
 * 健康检查：已加载的书目规模与索引规模。
 *
 * ``ready`` 表示检索索引是否已建好（服务可用）；``indexing`` 说的是"此刻建到
 * 哪一步了"，所以服务就绪之后它仍然有值——惰性构建时前端靠它显示进度。
 */
export interface HealthResponse {
  status: string
  ready: boolean
  indexing: IndexProgress
  books_loaded: number
  books_with_source: number
  total_chapters: number
  total_passages: number
  source_indexed: number
  source_skipped: string[]
  categories: string[]
}

/** 一条求教记录。 */
export interface HistoryItem {
  id: number
  question: string
  answer: string
  /** 产出回答的模型；null 表示本地检索降级 */
  model: string | null
  llm_used: boolean
  retrieved_count: number
  /** 所属话题；升级前的老记录为 null */
  conversation_id: string | null
  /** 本地时区的 ISO 8601 */
  created_at: string
  /** Unix 时间戳（秒） */
  created_ts: number
}

/**
 * 记录列表。
 *
 * ``available=False`` 时列表为空、``error`` 里是原因——这是接口层面的
 * **优雅降级**：数据库建不出来（程序目录只读、磁盘满）不该让界面报错，
 * 而应该照常渲染、顺手把原因说清楚。
 */
export interface HistoryListResponse {
  available: boolean
  error: string
  total: number
  items: HistoryItem[]
}

/** 存储概况：有多少条、保留多久、下次什么时候清理。 */
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

/** 建索引的进度快照。启动画面的进度条读它。 */
export interface IndexProgress {
  ratio: number
  stage: string
}

/** 单条感悟的响应模型。 */
export interface InsightItem {
  id: number
  text: string
  interpretation: string
  source: string
  book_id: string
  themes: string[]
}

/** 感悟列表响应。 */
export interface InsightListResponse {
  total: number
  items: InsightItem[]
}

/** 笔记里写下的一句互参原文。 */
export interface KbCrossRef {
  name: string
  detail: string
}

/** 一条边。``label`` 为空的边表示"关系成立但没有留下说明"。 */
export interface KbEdge {
  source: string
  target: string
  kind: KbEdgeKind
  /** 边上的说明。空串表示「关系成立但没留下说明」 */
  label: string
  weight: number
}

export type KbEdgeKind = 'theme' | 'cross' | 'part'

/** 一张可渲染的图。 */
export interface KbGraph {
  nodes: KbNode[]
  edges: KbEdge[]
  stats: Record<string, unknown>
}

/** 一条双链。``direction`` 为 ``out`` 时 ``node_id`` 是目标，``in`` 时是来源。 */
export interface KbLink {
  node_id: string
  label: string
  kind: KbEdgeKind
  edge_label: string
  direction: KbLinkDirection
}

export type KbLinkDirection = 'out' | 'in'

/** 图上的一个节点。``meta`` 内容随 kind 变化，见服务层说明。 */
export interface KbNode {
  id: string
  kind: KbNodeKind
  label: string
  /** 关联边数。界面据它决定节点大小 */
  degree: number
  meta: KbNodeMeta
}

/** 一个节点打开后的全部内容。 */
export interface KbNodeDetail {
  node: KbNode
  outgoing: KbLink[]
  backlinks: KbLink[]
  theme_rows: KbThemeRow[]
  cross_refs: KbCrossRef[]
}

export type KbNodeKind = 'book' | 'theme' | 'chapter'

/** 节点上的附属信息。**按 kind 取用**：书的字段与主题的字段不重叠。
 *
 * 后端把它声明成 `dict[str, Any]`（同一张图里有三类节点，meta 各装各的），
 * 这里写成可选字段集，前端才不用先断言再取键。
 */
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

/** 某书在某主题下的判断与代表章句。 */
export interface KbThemeRow {
  theme: string
  book_id: string
  book_title: string
  judgment: string
  quote: string
}

/**
 * 用户自填的模型端点。
 *
 * 三个字段全空即"用内置的默认模型"。只填一半（有地址没 Key）视同全空——
 * 见 :meth:`EndpointOverride.from_payload`，拿半截配置去试探只会换来一次
 * 注定失败的请求。
 */
export interface LLMEndpoint {
  /** 接口地址，如 https://api.example.com/v1 */
  base_url?: string
  /** API Key */
  api_key?: string
  /** 模型名；留空则由应用自动挑选 */
  model?: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface MeResponse {
  user: UserInfo | null
}

/** 成了，而且有话要带给用户。 */
export interface MessageResponse {
  ok: boolean
  message: string
}

/**
 * 只要一个"成了"。
 *
 * 那些没有别的话要回的写操作（登出、重置密码、改一行数据）用它，
 * 免得每个接口各返回一个裸 dict，在契约里留下一片空白。
 */
export interface OkResponse {
  ok: boolean
}

/** 自定义端点的连通性报告。 */
export interface ProbeResult {
  ok: boolean
  base_url: string
  model: string
  models: string[]
  error: string
}

/** 画像全貌。 */
export interface ProfileResponse {
  available: boolean
  error: string
  /** 形象性别：male / female */
  avatar: Avatar
  total: number
  traits: TraitItem[]
  /** 全部分类，界面按它排引线 */
  categories: string[]
  /** 上次归纳之后又问了多少条（最多 EXTRACT_SOURCE_LIMIT 条）。界面靠它决定要不要自动归纳一次。 */
  pending: number
  /** 最像你的一位历史人物 */
  figure: FigureInfo
}

/**
 * 公共书架里由用户贡献的一本书。
 *
 * ``from_user_id`` 可以是 ``null``：管理员手动加的书没有贡献者
 * （见 ``public_books`` 表的注释）。类型写成 ``int`` 会在那种行上校验失败，
 * 把一次正常的读取变成 500。
 */
export interface PublicBookRow {
  id: number
  /** 公共书号，形如 u01——u 前缀把它与内置的 01…15 区分开 */
  book_id: string
  title: string
  author: string
  category: string
  from_user_id: number | null
  created_at: string
}

export interface RegisterRequest {
  /** 邮箱，即账号 */
  email: string
  /** 密码，至少 8 位 */
  password: string
  /** 昵称，可留空 */
  display_name?: string
}

export interface ResetPasswordRequest {
  new_password: string
}

export interface ReviewRequest {
  approve: boolean
  note?: string
  /** 进公共书架时归入的分类 */
  category?: string
}

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

/** 改/删数据库某一行。``rowid`` 只有插入时才有。 */
export interface RowMutationResponse {
  ok: boolean
  rowid: number | null
}

export interface SearchRequest {
  title?: string
  author?: string
  limit?: number
}

/** 检索响应。 */
export interface SearchResponse {
  query: string
  total: number
  results: SearchResultItem[]
}

/** 单条检索结果。 */
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

export type SearchResultKind = 'notes' | 'source' | 'shelf'

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
  /** 驳回原因，只有 visibility 为 rejected 时有内容 */
  review_note: string
  created_at: string
  updated_at: string
}

export interface ShelfResponse {
  total: number
  counts: Record<string, number>
  books: ShelfBook[]
}

export type ShelfStatus = 'wish' | 'reading' | 'done'

export type ShelfVisibility = 'private' | 'pending' | 'public' | 'rejected'

/** 原典分块。``has_more`` 为真时前端可继续请求下一块。 */
export interface SourceChunk {
  book_id: string
  title: string
  content: string
  offset: number
  limit: number
  total: number
  has_more: boolean
}

/** 主题列表响应。 */
export interface ThemeListResponse {
  themes: string[]
  counts: Record<string, number>
}

/** 一个话题：一次会话里的连续追问聚成的一张卡片。 */
export interface TopicItem {
  /** 话题 id；老记录是 solo:<记录id> */
  id: string
  /** 话题的第一问 */
  title: string
  question_count: number
  first_ts: number
  last_ts: number
  latest_question: string
  latest_answer: string
}

/** 话题列表。``total`` 是**话题**数，不是记录数。 */
export interface TopicListResponse {
  available: boolean
  error: string
  /** 话题数，不是记录数 */
  total: number
  items: TopicItem[]
}

/** 一条画像特征。 */
export interface TraitItem {
  id: number
  /** 分类：性格 / 年龄 / 爱好 / 生活条件 / 成熟度 / 专业 / 规划。后端是封闭集合，界面把它译成标签，不要当成自由文本处理 */
  category: string
  content: string
  /** 依据：用户说过的哪句话 */
  evidence: string
  /** 模型的把握程度，0~1 */
  confidence: number
}

export interface UpdateBookRequest {
  status: string | null
  title: string | null
  author: string | null
}

export interface UpdateUserRequest {
  is_admin: boolean
}

/** 对外的用户信息。**绝不包含密码哈希与 salt。** */
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

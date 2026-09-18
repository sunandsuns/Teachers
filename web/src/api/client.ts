/** 后端 API 客户端：唯一的网络访问层，页面组件不得直接 fetch。
 *
 * 数据形状在 `types.ts`，这里只管怎么发请求。
 */

import { activeLang, tCurrent, type Lang } from '../i18n/messages'
import type {
  AskResponse,
  AskStatus,
  Avatar,
  BookSummary,
  ChapterDetail,
  ChapterSummary,
  ChatTurn,
  DeleteResult,
  ExtractResult,
  FigureResult,
  HistoryListResponse,
  HistoryStatus,
  InsightItem,
  InsightListResponse,
  KbGraph,
  KbNode,
  KbNodeDetail,
  LLMEndpoint,
  ProbeResult,
  ProfileResponse,
  SearchKind,
  SearchResponse,
  SourceChunk,
  ThemeListResponse,
  TopicListResponse,
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
    // 后端给了 detail 就用它（那是更具体的诊断信息），没给才用这句兜底。
    // 这里在 React 之外，只能读"当前语言"而不是 hook。
    const message = detail?.detail ?? tCurrent('error.requestFailed', { status: resp.status })
    throw new Error(message)
  }
  return resp.json() as Promise<T>
}

/** 求教时随行带的会话信息：追问要接得上文，也要知道自己属于哪个话题。 */
export interface AskContext {
  /** 最近几轮问答（新的在后） */
  history?: ChatTurn[]
  /** 所属话题；不带则后端新开一个，响应里回传 */
  conversationId?: string
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

  /** 求教。`llm` 省略时用后端内置的默认模型，见 `useModelSettings`。
   *
   * `lang` 决定**回答用什么语言写**：语料是中文的，检索永远在中文里进行，
   * 但英文界面下模型会用英文作答、降级文案也换英文。
   *
   * `context.history` 是最近几轮问答。**追问靠它接上文**——不带的话，后端收到
   * 的只是一个孤零零的新问题，回答会从头再讲一遍。
   * `context.conversationId` 决定这次归到哪个话题下（不给就新开一个）。 */
  ask: (
    question: string,
    topK = 5,
    llm?: LLMEndpoint | null,
    lang: Lang = activeLang(),
    context: AskContext = {},
  ) =>
    request<AskResponse>('/ask', {
      method: 'POST',
      body: JSON.stringify({
        question,
        top_k: topK,
        lang,
        ...(context.conversationId ? { conversation_id: context.conversationId } : {}),
        // 空数组就别发这个字段，没必要让请求体白带一段
        ...(context.history?.length ? { history: context.history } : {}),
        ...(llm ? { llm } : {}),
      }),
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

  /** 话题列表：一次会话里的连续追问聚成一张卡片。页面用它，不用平铺的列表。 */
  listTopics: (limit = 20, offset = 0) =>
    request<TopicListResponse>(`/history/topics?limit=${limit}&offset=${offset}`),

  /** 一个话题里的全部问答，按时间正序（读起来就是一段对话）。 */
  topicRecords: (topicId: string) =>
    request<HistoryListResponse>(`/history/topics/${encodeURIComponent(topicId)}`),

  deleteTopic: (topicId: string) =>
    request<DeleteResult>(`/history/topics/${encodeURIComponent(topicId)}`, {
      method: 'DELETE',
    }),

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

  // 「画像」——从问过的话里归纳出的"你是谁"。数据与历史记录同一个库。
  getProfile: () => request<ProfileResponse>('/profile'),

  /** 归纳画像。**会阻塞几十秒**（要走一次模型），所以放在页面里异步触发，
   *  不要挡住首屏渲染。
   *
   *  `lang` 决定特征正文用哪种语言写；分类始终是中文封闭集合。 */
  extractProfile: (lang: Lang = activeLang()) =>
    request<ExtractResult>('/profile/extract', {
      method: 'POST',
      body: JSON.stringify({ lang }),
    }),

  /** 切换形象性别。存后端而不是浏览器本地：它属于画像这份数据。
   *  它同时是**历史人物的筛选池**——男册只在男性名录里挑人。 */
  setAvatar: (avatar: Avatar) =>
    request<{ avatar: Avatar }>('/profile/avatar', {
      method: 'PUT',
      body: JSON.stringify({ gender: avatar }),
    }),

  /** 让模型重新评一次"最像你的一位历史人物"。**会阻塞几十秒**。
   *
   *  后端不判断"该不该评"（那是读到画像时给出的 `needs_refresh` 的活儿），
   *  被调用就评——用户也可能就是想让它重看一遍。 */
  evaluateFigure: (lang: Lang = activeLang()) =>
    request<FigureResult>('/profile/figure', {
      method: 'POST',
      body: JSON.stringify({ lang }),
    }),

  /** 删掉一条特征。用户不认同的判断就该能抹掉。 */
  deleteTrait: (id: number) =>
    request<DeleteResult>(`/profile/traits/${id}`, { method: 'DELETE' }),

  /** 清空画像（**不**动问答记录）。 */
  clearProfile: () => request<DeleteResult>('/profile', { method: 'DELETE' }),

  // 「知识库」——15 部书与 8 个主题之间的双链与关系图谱。
  /** 全图。默认不含 352 个章节节点，那会把书与书之间的结构淹掉。 */
  kbGraph: (chapters = false) =>
    request<KbGraph>(`/kb/graph?chapters=${chapters}`),

  /** 以某个节点为中心的局部图（焦点 + 邻居）。书节点会带上自己的章节。 */
  kbLocal: (nodeId: string, chapters = true) =>
    request<KbGraph>(
      `/kb/nodes/${encodeURIComponent(nodeId)}/local?chapters=${chapters}`,
    ),

  /** 节点详情：出链、反向链接、主题明细、互参原文。 */
  kbNode: (nodeId: string) =>
    request<KbNodeDetail>(`/kb/nodes/${encodeURIComponent(nodeId)}`),

  /** 按名字找节点。空查询返回关联最多的若干节点。 */
  kbSearch: (q = '', limit = 20) =>
    request<KbNode[]>(`/kb/search?q=${encodeURIComponent(q)}&limit=${limit}`),
}

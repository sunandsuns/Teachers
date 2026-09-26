import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { api } from '../api/client'
import { AuthProvider } from '../features/auth/AuthProvider'

vi.mock('../api/client', () => ({
  api: {
    me: vi.fn(),
    listBooks: vi.fn(),
    getBook: vi.fn(),
    listChapters: vi.fn(),
    getChapter: vi.fn(),
    getSource: vi.fn(),
    search: vi.fn(),
    ask: vi.fn(),
    probeModel: vi.fn(),
    askStatus: vi.fn(),
    listHistory: vi.fn(),
    listTopics: vi.fn(),
    topicRecords: vi.fn(),
    historyStatus: vi.fn(),
    deleteHistory: vi.fn(),
    deleteTopic: vi.fn(),
    deleteSelected: vi.fn(),
    clearHistory: vi.fn(),
    dailyInsight: vi.fn(),
    randomInsight: vi.fn(),
    insightThemes: vi.fn(),
    insightsByTheme: vi.fn(),
    insightsByBook: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

/** 已登录的普通用户。
 *
 * 这些用例走的是**整个应用**（`<App />`），而 `App` 里的路由表把除书架与
 * 阅读页之外的路由都圈进了 `RequireAuth`。所以不套 `AuthProvider`、或者
 * `me` 返回 null 的话，点「寻章」「求教」「回响」看到的会是登录门，
 * 断言的不是页面而是门——那种"通过"毫无意义。
 */
const VIEWER = {
  id: 2,
  email: 'alice@example.com',
  display_name: '小艾',
  name: '小艾',
  is_admin: false,
  created_at: '2026-01-01T00:00:00+00:00',
}

/** 挂上真实的 Provider 栈再渲染整个应用。
 *
 * `AuthProvider` 必须在 `MemoryRouter` 里面——和 `main.tsx` 的嵌套顺序一致，
 * 将来它要是用上路由钩子，这里才不会莫名其妙地炸。 */
function renderApp(entries: string[] = ['/']) {
  return render(
    <MemoryRouter initialEntries={entries}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

/** 集成测试：从书架点进书 → 选章节 → 看到 Markdown 内容。 */
describe('阅读流程', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.me.mockResolvedValue({ user: VIEWER })
    mockedApi.listBooks.mockResolvedValue([
      { book_id: '02', title: '厚黑学', author: '李宗吾', category: '处世', chapter_count: 2, has_source: false },
    ])
    mockedApi.getBook.mockResolvedValue(
      { book_id: '02', title: '厚黑学', author: '李宗吾', category: '处世', chapter_count: 2, has_source: false },
    )
    mockedApi.listChapters.mockResolvedValue([
      { chapter_id: '01', title: '缘起', book_id: '02' },
      { chapter_id: '02', title: '三重境界', book_id: '02' },
    ])
    mockedApi.getChapter.mockResolvedValue({
      chapter_id: '01', title: '缘起', book_id: '02',
      content: '## 缘起\n\n千古不传之秘，不过面厚心黑而已。',
    })
    window.history.replaceState({}, '', '/')
  })

  it('书架 → 书页 → 章节', async () => {
    renderApp()
    const user = userEvent.setup()

    await user.click(await screen.findByText('厚黑学'))
    await waitFor(() => expect(mockedApi.listChapters).toHaveBeenCalledWith('02'))

    await user.click(await screen.findByText('缘起'))
    await waitFor(() =>
      expect(screen.getByText('千古不传之秘，不过面厚心黑而已。')).toBeTruthy(),
    )
  })
})

/** 集成测试：求教页输入问题 → 显示回答与引用信息。 */
describe('问答流程', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.me.mockResolvedValue({ user: VIEWER })
    mockedApi.ask.mockResolvedValue({
      question: '如何面对挫折',
      answer: '天行健，君子以自强不息。逆境是蓄力期。',
      retrieved_count: 5,
      llm_used: false,
      model: null,
      history_id: 1,
      conversation_id: 't1',
    })
    window.history.replaceState({}, '', '/ask')
  })

  it('提问后展示回答', async () => {
    renderApp(['/ask'])
    const user = userEvent.setup()

    const input = await screen.findByPlaceholderText('输入你的问题或困境…')
    await user.type(input, '如何面对挫折')
    await user.click(screen.getByRole('button', { name: '求教' }))

    await waitFor(() =>
      expect(screen.getByText('天行健，君子以自强不息。逆境是蓄力期。')).toBeTruthy(),
    )
    expect(screen.getByText('引用 5 段经典')).toBeTruthy()
    expect(screen.getByText('本地检索模式')).toBeTruthy()
    // 回答会自动存进「回响」，界面上得留一个去处的入口
    expect(screen.getByRole('link', { name: '已存入回响' })).toBeTruthy()
  })

  it('带 q 参数进来时预填问题（「回响」的再问一次）', async () => {
    renderApp(['/ask?q=迷茫时该怎么办'])

    const input = (await screen.findByPlaceholderText(
      '输入你的问题或困境…',
    )) as HTMLTextAreaElement
    expect(input.value).toBe('迷茫时该怎么办')
  })
})

/** 集成测试：导航栏五个入口可切换。 */
describe('导航', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.me.mockResolvedValue({ user: VIEWER })
    mockedApi.listBooks.mockResolvedValue([])
    mockedApi.listHistory.mockResolvedValue({ available: true, error: '', total: 0, items: [] })
    mockedApi.listTopics.mockResolvedValue({ available: true, error: '', total: 0, items: [] })
    mockedApi.topicRecords.mockResolvedValue({ available: true, error: '', total: 0, items: [] })
    mockedApi.historyStatus.mockResolvedValue({
      available: true,
      error: '',
      db_path: 'C:/data/history.db',
      total: 0,
      retention_days: 15,
      last_purge_at: null,
      next_purge_at: null,
      size_bytes: 0,
    })
    mockedApi.dailyInsight.mockResolvedValue({
      id: 0, text: 't', interpretation: 'i', source: 's', book_id: '01', themes: ['修心'],
    })
    mockedApi.randomInsight.mockResolvedValue({
      id: 0, text: 't', interpretation: 'i', source: 's', book_id: '01', themes: ['修心'],
    })
    mockedApi.insightThemes.mockResolvedValue({ themes: [], counts: {} })
    window.history.replaceState({}, '', '/')
  })

  it('寻章、求教、回响与感悟入口渲染对应页面', async () => {
    renderApp()
    const user = userEvent.setup()

    // 先等顶栏出现再点：`/` 现在也要登录，首帧是"登录态还没回来"的兜底。
    await user.click(await screen.findByText('寻章'))
    await waitFor(() => expect(screen.getByPlaceholderText('输入关键词，例如：上善若水')).toBeTruthy())

    await user.click(screen.getByText('求教'))
    await waitFor(() => expect(screen.getByPlaceholderText('输入你的问题或困境…')).toBeTruthy())

    await user.click(screen.getByText('回响'))
    await waitFor(() => expect(screen.getByText(/还没有求教记录/)).toBeTruthy())

    await user.click(screen.getByText('感悟'))
    await waitFor(() => expect(screen.getByText('按主题浏览')).toBeTruthy())
  })
})

/** 集成测试：在**整个应用里**走一遍勾选删除。
 *
 * 单页面的测试已经覆盖了勾选的细节，这一条额外盯住两件只有装在一起才会出问题的事：
 * 页面是按路由懒加载的（点进「回响」时要等那块 chunk 到位），以及
 * 列表页拿到的数据确实来自接口而不是别的页面的残留。
 */
describe('回响的勾选删除（整个应用里）', () => {
  const NOW = Date.now() / 1000

  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.me.mockResolvedValue({ user: VIEWER })
    mockedApi.listBooks.mockResolvedValue([])
    mockedApi.listTopics.mockResolvedValue({
      available: true,
      error: '',
      total: 1,
      items: [
        {
          id: 't1',
          title: '工作中遇到小人怎么办？',
          question_count: 2,
          first_ts: NOW - 60,
          last_ts: NOW,
          latest_question: '那要是躲不开呢？',
          latest_answer: '敬而远之。',
        },
      ],
    })
    mockedApi.historyStatus.mockResolvedValue({
      available: true,
      error: '',
      db_path: 'C:/data/history.db',
      total: 2,
      retention_days: 15,
      last_purge_at: null,
      next_purge_at: null,
      size_bytes: 4096,
    })
    mockedApi.deleteSelected.mockResolvedValue({ deleted: 2 })
    window.history.replaceState({}, '', '/')
  })

  it('从导航进回响，勾一段再删掉', async () => {
    renderApp()
    const user = userEvent.setup()

    // 同上：顶栏要等登录态回来才渲染
    await user.click(await screen.findByText('回响'))
    await waitFor(() => expect(screen.getByText('工作中遇到小人怎么办？')).toBeTruthy())

    await user.click(screen.getByRole('button', { name: '选择' }))
    await user.click(
      screen.getByRole('checkbox', { name: '勾选这段对话：工作中遇到小人怎么办？' }),
    )
    expect(screen.getByText('已选 1 个话题 · 0 条记录')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: '删除选中' }))
    await user.click(await screen.findByRole('button', { name: '确认删除' }))

    await waitFor(() =>
      expect(mockedApi.deleteSelected).toHaveBeenCalledWith({ topics: ['t1'], ids: [] }),
    )
  })
})

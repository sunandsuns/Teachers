import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: {
    listBooks: vi.fn(),
    getBook: vi.fn(),
    listChapters: vi.fn(),
    getChapter: vi.fn(),
    getSource: vi.fn(),
    search: vi.fn(),
    ask: vi.fn(),
    probeModel: vi.fn(),
    askStatus: vi.fn(),
    dailyInsight: vi.fn(),
    randomInsight: vi.fn(),
    insightThemes: vi.fn(),
    insightsByTheme: vi.fn(),
    insightsByBook: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

/** 集成测试：从书架点进书 → 选章节 → 看到 Markdown 内容。 */
describe('阅读流程', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
    render(<MemoryRouter><App /></MemoryRouter>)
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
    mockedApi.ask.mockResolvedValue({
      question: '如何面对挫折',
      answer: '天行健，君子以自强不息。逆境是蓄力期。',
      retrieved_count: 5,
      llm_used: false,
      model: null,
    })
    window.history.replaceState({}, '', '/ask')
  })

  it('提问后展示回答', async () => {
    render(
      <MemoryRouter initialEntries={['/ask']}>
        <App />
      </MemoryRouter>,
    )
    const user = userEvent.setup()

    const input = await screen.findByPlaceholderText('输入你的问题或困境…')
    await user.type(input, '如何面对挫折')
    await user.click(screen.getByRole('button', { name: '求教' }))

    await waitFor(() =>
      expect(screen.getByText('天行健，君子以自强不息。逆境是蓄力期。')).toBeTruthy(),
    )
    expect(screen.getByText('引用 5 段经典')).toBeTruthy()
    expect(screen.getByText('本地检索模式')).toBeTruthy()
  })
})

/** 集成测试：导航栏三个入口可切换。 */
describe('导航', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.listBooks.mockResolvedValue([])
    mockedApi.dailyInsight.mockResolvedValue({
      id: 0, text: 't', interpretation: 'i', source: 's', book_id: '01', themes: ['修心'],
    })
    mockedApi.randomInsight.mockResolvedValue({
      id: 0, text: 't', interpretation: 'i', source: 's', book_id: '01', themes: ['修心'],
    })
    mockedApi.insightThemes.mockResolvedValue({ themes: [], counts: {} })
    window.history.replaceState({}, '', '/')
  })

  it('寻章、求教与感悟入口渲染对应页面', async () => {
    render(<MemoryRouter><App /></MemoryRouter>)
    const user = userEvent.setup()

    await user.click(screen.getByText('寻章'))
    await waitFor(() => expect(screen.getByPlaceholderText('输入关键词，例如：上善若水')).toBeTruthy())

    await user.click(screen.getByText('求教'))
    await waitFor(() => expect(screen.getByPlaceholderText('输入你的问题或困境…')).toBeTruthy())

    await user.click(screen.getByText('感悟'))
    await waitFor(() => expect(screen.getByText('按主题浏览')).toBeTruthy())
  })
})

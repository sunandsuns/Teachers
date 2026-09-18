import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Reader from '../pages/Reader'
import Advisor from '../pages/Advisor'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: {
    listBooks: vi.fn(),
    getBook: vi.fn(),
    listChapters: vi.fn(),
    getChapter: vi.fn(),
    getSource: vi.fn(),
    ask: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

function renderReader(bookId: string) {
  return render(
    <MemoryRouter initialEntries={[`/books/${bookId}`]}>
      <Routes>
        <Route path="/books/:bookId" element={<Reader />} />
      </Routes>
    </MemoryRouter>,
  )
}

function chunk(overrides: Record<string, unknown> = {}) {
  return {
    book_id: '14',
    title: '资治通鉴',
    content: '卷一 周纪一',
    offset: 0,
    limit: 20000,
    total: 3216638,
    has_more: true,
    ...overrides,
  }
}

/** 点开「原典全文」页签 */
async function openSourceTab(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByText('原典全文'))
}

describe('Reader 原典分页', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.getBook.mockResolvedValue({
      book_id: '14', title: '资治通鉴', author: '司马光',
      category: '历史文献', chapter_count: 12, has_source: true,
    })
    mockedApi.listChapters.mockResolvedValue([])
  })

  it('大书首块加载后显示翻页进度与按钮', async () => {
    mockedApi.getSource.mockResolvedValue(chunk())
    const user = userEvent.setup()
    renderReader('14')

    await openSourceTab(user)

    await waitFor(() => expect(screen.getByText(/卷一 周纪一/)).toBeTruthy())
    expect(screen.getByText(/已载入 6 \/ 3,216,638 字/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '载入后续' })).toBeTruthy()
  })

  it('点「载入后续」按已读长度追加下一块', async () => {
    mockedApi.getSource
      .mockResolvedValueOnce(chunk())
      .mockResolvedValueOnce(
        chunk({ content: '卷二 周纪二', offset: 20000, has_more: false }),
      )

    const user = userEvent.setup()
    renderReader('14')
    await openSourceTab(user)
    await waitFor(() => expect(screen.getByText(/卷一/)).toBeTruthy())

    await user.click(screen.getByRole('button', { name: '载入后续' }))

    await waitFor(() => expect(screen.getByText(/卷二 周纪二/)).toBeTruthy())
    // 前一块仍在，是"累加"而不是"替换"
    expect(screen.getByText(/卷一/)).toBeTruthy()
    // 下一块的 offset 应等于已读字数（'卷一 周纪一' 共 6 字）
    expect(mockedApi.getSource).toHaveBeenLastCalledWith('14', 6)
    expect(screen.queryByRole('button', { name: '载入后续' })).toBeNull()
  })

  it('短书不显示翻页控件', async () => {
    mockedApi.getSource.mockResolvedValue(
      chunk({ book_id: '08', content: '道可道，非常道。', total: 11, limit: 20000, has_more: false }),
    )
    const user = userEvent.setup()
    renderReader('08')
    await openSourceTab(user)

    await waitFor(() => expect(screen.getByText(/道可道/)).toBeTruthy())
    expect(screen.queryByRole('button', { name: '载入后续' })).toBeNull()
  })

  it('原典加载失败时显示错误', async () => {
    mockedApi.getSource.mockRejectedValue(new Error('原典读取失败'))
    const user = userEvent.setup()
    renderReader('14')
    await openSourceTab(user)

    await waitFor(() => expect(screen.getByText('原典读取失败')).toBeTruthy())
  })
})

describe('Advisor 模型标识', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('走 AI 时显示实际模型名', async () => {
    mockedApi.ask.mockResolvedValue({
      question: '如何面对挫折',
      answer: '天行健，君子以自强不息。',
      retrieved_count: 3,
      llm_used: true,
      model: 'deepseek-v4-pro-0813',
      history_id: 1,
      conversation_id: 't1',
    })

    const user = userEvent.setup()
    render(<MemoryRouter><Advisor /></MemoryRouter>)
    await user.type(
      await screen.findByPlaceholderText('输入你的问题或困境…'),
      '如何面对挫折',
    )
    await user.click(screen.getByRole('button', { name: '求教' }))

    await waitFor(() =>
      expect(screen.getByText('AI 深度解读 · deepseek-v4-pro-0813')).toBeTruthy(),
    )
  })

  it('降级时显示本地检索模式', async () => {
    mockedApi.ask.mockResolvedValue({
      question: '如何面对挫折',
      answer: '天行健，君子以自强不息。',
      retrieved_count: 3,
      llm_used: false,
      model: null,
      history_id: 1,
      conversation_id: 't1',
    })

    const user = userEvent.setup()
    render(<MemoryRouter><Advisor /></MemoryRouter>)
    await user.type(
      await screen.findByPlaceholderText('输入你的问题或困境…'),
      '如何面对挫折',
    )
    await user.click(screen.getByRole('button', { name: '求教' }))

    await waitFor(() => expect(screen.getByText('本地检索模式')).toBeTruthy())
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Search from '../pages/Search'
import Reader from '../pages/Reader'
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
    dailyInsight: vi.fn(),
    randomInsight: vi.fn(),
    insightThemes: vi.fn(),
    insightsByTheme: vi.fn(),
    insightsByBook: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

const HIT = {
  book_id: '14',
  book_title: '资治通鉴',
  chapter_id: '03',
  chapter_title: '才与德',
  content: '才者，德之资也；德者，才之帅也。',
  score: 0.8712,
  source: '《资治通鉴》· 才与德',
  kind: 'notes' as const,
  offset: 0,
}

const SOURCE_HIT = {
  book_id: '08',
  book_title: '道德经',
  chapter_id: '',
  chapter_title: '原典全文',
  content: '上善若水。水善利万物而不争。',
  score: 0.912,
  source: '《道德经》· 原典全文',
  kind: 'source' as const,
  offset: 2400,
}

async function submitQuery(keyword: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('检索关键词'), keyword)
  await user.click(screen.getByRole('button', { name: '检索' }))
}

const NO_SOURCE_BOOK = {
  book_id: '14', title: '资治通鉴', author: '司马光',
  category: '历史文献', chapter_count: 8, has_source: false,
}

/** Reader 页依赖：原典文本从 offset 处开始分页返回。 */
function mockReaderBasics() {
  mockedApi.getBook.mockResolvedValue(NO_SOURCE_BOOK)
  mockedApi.listChapters.mockResolvedValue([
    { chapter_id: '03', title: '才与德', book_id: '14' },
  ])
  mockedApi.getChapter.mockResolvedValue({
    chapter_id: '03', title: '才与德', book_id: '14',
    content: '才者，德之资也。',
  })
}

describe('寻章页面', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('检索后展示命中结果、出处与相关度', async () => {
    mockedApi.search.mockResolvedValue({ query: '才者德之资', total: 1, results: [HIT] })
    render(
      <MemoryRouter>
        <Search />
      </MemoryRouter>,
    )

    await submitQuery('才者德之资')

    await waitFor(() => expect(screen.getByText('《资治通鉴》· 才与德')).toBeTruthy())
    expect(mockedApi.search).toHaveBeenCalledWith('才者德之资', 12, 'all')
    expect(screen.getByText('命中 1 段')).toBeTruthy()
    expect(screen.getByText('相关度 0.871')).toBeTruthy()
  })

  it('原典命中打上「原典」标记，笔记命中打上「笔记」标记', async () => {
    mockedApi.search.mockResolvedValue({
      query: '上善若水', total: 2, results: [SOURCE_HIT, HIT],
    })
    render(
      <MemoryRouter>
        <Search />
      </MemoryRouter>,
    )

    await submitQuery('上善若水')

    await waitFor(() => expect(screen.getByText('原典')).toBeTruthy())
    expect(screen.getByText('笔记')).toBeTruthy()
  })

  it('切换「原典全文」标签后按 kind 重新检索', async () => {
    mockedApi.search.mockResolvedValue({ query: '上善若水', total: 1, results: [SOURCE_HIT] })
    render(
      <MemoryRouter>
        <Search />
      </MemoryRouter>,
    )

    await submitQuery('上善若水')
    expect(mockedApi.search).toHaveBeenLastCalledWith('上善若水', 12, 'all')

    await userEvent.setup().click(screen.getByRole('button', { name: '原典全文' }))
    await waitFor(() =>
      expect(mockedApi.search).toHaveBeenLastCalledWith('上善若水', 12, 'source'),
    )
  })

  it('空结果给出提示', async () => {
    mockedApi.search.mockResolvedValue({ query: 'zzz', total: 0, results: [] })
    render(
      <MemoryRouter>
        <Search />
      </MemoryRouter>,
    )

    await submitQuery('zzz')

    await waitFor(() => expect(screen.getByText('没有找到相关段落，换个词试试')).toBeTruthy())
  })

  it('检索失败时展示错误信息', async () => {
    mockedApi.search.mockRejectedValue(new Error('服务不可用'))
    render(
      <MemoryRouter>
        <Search />
      </MemoryRouter>,
    )

    await submitQuery('任意')

    await waitFor(() => expect(screen.getByText('服务不可用')).toBeTruthy())
  })

  it('未输入时不发起请求', async () => {
    render(
      <MemoryRouter>
        <Search />
      </MemoryRouter>,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '检索' }))
    expect(mockedApi.search).not.toHaveBeenCalled()
  })

  it('点击示例词直接检索', async () => {
    mockedApi.search.mockResolvedValue({ query: '自强不息', total: 0, results: [] })
    render(
      <MemoryRouter>
        <Search />
      </MemoryRouter>,
    )

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '自强不息' }))

    await waitFor(() => expect(mockedApi.search).toHaveBeenCalledWith('自强不息', 12, 'all'))
  })
})

describe('寻章 → 阅读 深链', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockReaderBasics()
  })

  it('笔记结果链接带 chapter 参数，Reader 直接打开该章节', async () => {
    mockedApi.search.mockResolvedValue({ query: 'q', total: 1, results: [HIT] })
    render(
      <MemoryRouter initialEntries={['/search']}>
        <Routes>
          <Route path="/search" element={<Search />} />
          <Route path="/books/:bookId" element={<Reader />} />
        </Routes>
      </MemoryRouter>,
    )

    await submitQuery('q')
    await userEvent.setup().click(await screen.findByText('《资治通鉴》· 才与德'))

    await waitFor(() => expect(mockedApi.getChapter).toHaveBeenCalledWith('14', '03'))
    await waitFor(() => expect(screen.getByText('才者，德之资也。')).toBeTruthy())
  })

  it('原典结果链接带 offset，Reader 从该位置加载原典', async () => {
    mockedApi.search.mockResolvedValue({ query: 'q', total: 1, results: [SOURCE_HIT] })
    mockedApi.getSource.mockResolvedValue({
      book_id: '08', title: '道德经', content: '上善若水。水善利万物而不争。',
      offset: 2400, limit: 20000, total: 7728, has_more: false,
    })
    render(
      <MemoryRouter initialEntries={['/search']}>
        <Routes>
          <Route path="/search" element={<Search />} />
          <Route path="/books/:bookId" element={<Reader />} />
        </Routes>
      </MemoryRouter>,
    )

    await submitQuery('q')
    await userEvent.setup().click(await screen.findByText('《道德经》· 原典全文'))

    await waitFor(() => expect(mockedApi.getSource).toHaveBeenCalledWith('08', 2400))
    await waitFor(() => expect(screen.getByText('上善若水。水善利万物而不争。')).toBeTruthy())
  })
})

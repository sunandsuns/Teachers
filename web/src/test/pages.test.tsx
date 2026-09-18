import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import Library from '../pages/Library'
import Insights from '../pages/Insights'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: {
    listBooks: vi.fn(),
    getBook: vi.fn(),
    listChapters: vi.fn(),
    getChapter: vi.fn(),
    getSource: vi.fn(),
    listHistory: vi.fn(),
    listTopics: vi.fn(),
    topicRecords: vi.fn(),
    historyStatus: vi.fn(),
    deleteHistory: vi.fn(),
    deleteTopic: vi.fn(),
    clearHistory: vi.fn(),
    dailyInsight: vi.fn(),
    randomInsight: vi.fn(),
    insightThemes: vi.fn(),
    insightsByTheme: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

function renderPage(el: React.ReactElement) {
  return render(<BrowserRouter>{el}</BrowserRouter>)
}

describe('Library 页面', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('渲染书籍卡片', async () => {
    mockedApi.listBooks.mockResolvedValue([
      { book_id: '01', title: '易经', author: '周文王', category: '哲学', chapter_count: 5, has_source: true },
      { book_id: '02', title: '厚黑学', author: '李宗吾', category: '处世', chapter_count: 12, has_source: true },
    ])
    renderPage(<Library />)
    await waitFor(() => expect(screen.getByText('厚黑学')).toBeTruthy())
    expect(screen.getByText('易经')).toBeTruthy()
    expect(
      screen.getByText((_, el) => el?.tagName === 'P' && el.textContent === '5 章 · 含原典'),
    ).toBeTruthy()
  })

  it('加载失败时显示错误', async () => {
    mockedApi.listBooks.mockRejectedValue(new Error('网络错误'))
    renderPage(<Library />)
    await waitFor(() => expect(screen.getByText('网络错误')).toBeTruthy())
  })

  it('空书架显示提示', async () => {
    mockedApi.listBooks.mockResolvedValue([])
    renderPage(<Library />)
    await waitFor(() => expect(screen.getByText('书架还是空的')).toBeTruthy())
  })

  it('按分类筛选书目', async () => {
    mockedApi.listBooks.mockResolvedValue([
      { book_id: '13', title: '史记', author: '司马迁', category: '历史文献', chapter_count: 7, has_source: false },
      { book_id: '14', title: '资治通鉴', author: '司马光', category: '历史文献', chapter_count: 8, has_source: false },
      { book_id: '09', title: '论语', author: '孔子弟子辑录', category: '哲学', chapter_count: 9, has_source: false },
    ])
    renderPage(<Library />)
    await waitFor(() => expect(screen.getByText('史记')).toBeTruthy())
    expect(screen.getByText('论语')).toBeTruthy()

    await userEvent.setup().click(screen.getByRole('button', { name: /历史文献/ }))

    await waitFor(() => expect(screen.queryByText('论语')).toBeNull())
    expect(screen.getByText('史记')).toBeTruthy()
    expect(screen.getByText('资治通鉴')).toBeTruthy()
  })

  it('切回全部可恢复完整列表', async () => {
    mockedApi.listBooks.mockResolvedValue([
      { book_id: '13', title: '史记', author: '司马迁', category: '历史文献', chapter_count: 7, has_source: false },
      { book_id: '09', title: '论语', author: '孔子弟子辑录', category: '哲学', chapter_count: 9, has_source: false },
    ])
    renderPage(<Library />)
    await waitFor(() => expect(screen.getByText('史记')).toBeTruthy())

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /历史文献/ }))
    await waitFor(() => expect(screen.queryByText('论语')).toBeNull())

    await user.click(screen.getByRole('button', { name: /全部/ }))
    await waitFor(() => expect(screen.getByText('论语')).toBeTruthy())
  })
})

describe('Insights 页面', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('渲染今日感悟与主题标签', async () => {
    mockedApi.dailyInsight.mockResolvedValue({
      id: 3, text: '天行健，君子以自强不息。', interpretation: '效法天道奋发不止。',
      source: '《易经》·乾卦', book_id: '01', themes: ['立志', '恒心'],
    })
    mockedApi.randomInsight.mockResolvedValue({
      id: 1, text: '潜龙勿用。', interpretation: '时机未到先蓄力。',
      source: '《易经》·乾卦', book_id: '01', themes: ['进退'],
    })
    mockedApi.insightThemes.mockResolvedValue({
      themes: ['逆境', '修心'], counts: { '逆境': 5, '修心': 3 },
    })
    renderPage(<Insights />)
    await waitFor(() => expect(screen.getByText('今日感悟')).toBeTruthy())
    expect(screen.getByText(/天行健/)).toBeTruthy()
    expect(screen.getByText('逆境')).toBeTruthy()
  })
})

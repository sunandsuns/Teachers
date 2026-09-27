import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Reader from '../pages/Reader'
import Advisor from '../pages/Advisor'
import { api, peek } from '../api/client'

vi.mock('../api/client', async (importOriginal) => {
  // 真实导出照单全收——只把 `api` 换成假的。手写一份导出清单是脆的：
  // 模块新增一个导出（本轮的 `peek` 就是），十几个测试文件会一起挂，
  // 而报出来的错（"mock 里没有 peek"）跟这些用例要测的事毫无关系。
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: {
      listBooks: vi.fn(),
      getBook: vi.fn(),
      listChapters: vi.fn(),
      getChapter: vi.fn(),
      getSource: vi.fn(),
      ask: vi.fn(),
    },
    // `peek` 也换掉：真实的 `peek` 读的是 `client.ts` 里那份模块级缓存，而这里
    // `api` 是假的、什么都没写进去，所以真 `peek` 恒为 `undefined`——"命中缓存"
    // 这条路径根本测不到。只换 `getSource` 一个方法，其余照旧。
    peek: { ...actual.peek, getSource: vi.fn() },
  }
})

const mockedApi = vi.mocked(api)
const mockedPeek = vi.mocked(peek)

function renderReader(bookId: string, search = '') {
  return render(
    <MemoryRouter initialEntries={[`/books/${bookId}${search}`]}>
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
    // `clearAllMocks` 只清调用记录、**不清** `mockReturnValue`——不显式归零的话，
    // 一条用例设过的"缓存里有值"会漏给后面所有用例。
    mockedPeek.getSource.mockReturnValue(undefined)
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

/**
 * 原典正文的首帧。
 *
 * 切到原典页签才去拉正文（笔记页签不该为它付一次请求），所以 `active` 每次由
 * false 翻到 true 都是一次重新开始。原先那一下必然先置 `loading`，于是"切走
 * 再切回"时要先闪一帧「加载原典…」——哪怕那块正文就在 GET 缓存里躺着。
 *
 * 这里盯的**不是末态**（末态两种写法都对），而是"有没有真去请求"：命中缓存
 * 还照发请求的话，那一次 `loading` 就是屏幕上实打实的一闪。另外原典的 `text`
 * 是**累加**的，命中之后再发一次同 `offset` 的请求，回来的那块会被追加到刚
 * 恢复的正文后面——一整段重复，所以正文还得断言"恰好一块"。
 */
describe('Reader 原典首帧', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.getBook.mockResolvedValue({
      book_id: '14', title: '资治通鉴', author: '司马光',
      category: '历史文献', chapter_count: 12, has_source: true,
    })
    mockedApi.listChapters.mockResolvedValue([])
    mockedApi.getSource.mockResolvedValue(chunk())
    mockedPeek.getSource.mockReturnValue(undefined)
  })

  it('切回原典页签时直接用缓存的那一块：不请求、不进加载态', async () => {
    // 缓存里有这块正文 —— 正是"上次已经读过、现在切回来"的情形
    mockedPeek.getSource.mockReturnValue(chunk())
    const user = userEvent.setup()
    renderReader('14')

    await openSourceTab(user)
    expect(screen.getByText('卷一 周纪一')).toBeTruthy()

    // 切回笔记页签，再切过来一次
    await user.click(screen.getByText('理解笔记'))
    await openSourceTab(user)

    // 正文仍在，且**恰好一块**（精确匹配；若被拼了两遍就找不到了）
    expect(screen.getByText('卷一 周纪一')).toBeTruthy()
    // 加载提示一次都不该出现
    expect(screen.queryByText('加载原典…')).toBeNull()
    // 关键：压根没发请求。命中了还去请求的话，那次 `loading` 就是白闪的一帧
    expect(mockedApi.getSource).not.toHaveBeenCalled()
  })

  it('深链带 offset 进来时，要的是那个位置那一块，不是从头读', async () => {
    // 从「寻章」的原典命中跳进来：offset=120000。首块是从 12 万字处开始的，
    // 此时 `stateFromChunk` 走的是"追加"分支——旧正文为空，所以结果仍是一块。
    mockedPeek.getSource.mockReturnValue(
      chunk({ offset: 120000, content: '（第十二万字处）' }),
    )
    renderReader('14', '?tab=source&offset=120000')

    // 深链一进来 `active` 就是 true，所以正文那一块与书目、章节列表**同时**开跑；
    // 页面顶层要等书目回来才让出位置，这里用 findBy 等它落定。
    expect(await screen.findByText('（第十二万字处）')).toBeTruthy()
    expect(mockedPeek.getSource).toHaveBeenCalledWith('14', 120000)
    expect(mockedApi.getSource).not.toHaveBeenCalled()
  })

  it('缓存里没有这块时照常请求——切到原典页签不能什么都不做', async () => {
    const user = userEvent.setup()
    renderReader('14')
    await openSourceTab(user)

    await waitFor(() => expect(screen.getByText('卷一 周纪一')).toBeTruthy())
    expect(mockedApi.getSource).toHaveBeenCalledWith('14', 0)
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

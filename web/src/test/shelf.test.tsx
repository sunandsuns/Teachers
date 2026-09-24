import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { api } from '../api/client'
import type { ShelfBook } from '../api/types'
import ShelfPage from '../features/shelf/ShelfPage'
import { I18nProvider } from '../i18n'

vi.mock('../api/client', () => ({
  api: {
    listShelf: vi.fn(),
    searchBooks: vi.fn(),
    addShelfBook: vi.fn(),
    updateShelfBook: vi.fn(),
    removeShelfBook: vi.fn(),
    submitShelfBook: vi.fn(),
    cancelShelfBook: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

const CANDIDATE = {
  title: '活着',
  author: '余华',
  year: '2012',
  cover_url: '',
  source_key: 'OL25129388W',
  source: 'openlibrary',
  summary: '一个人和他命运之间的友情。',
  subjects: ['Fiction', 'China'],
}

const BOOK = {
  id: 7,
  title: '活着',
  author: '余华',
  year: '2012',
  cover_url: '',
  source_key: 'OL25129388W',
  summary: '',
  subjects: [],
  guide: '## 这本书在讲什么\n\n一个人和他命运之间的友情。',
  has_guide: true,
  status: 'wish' as const,
  visibility: 'private' as const,
  review_note: '',
  // `created_at` 用一个**明确在过去**的固定时刻，不要写"离现在很近的某刻"。
  //
  // 卡片上"导读生成中"的判定是 `Date.now() - created_at < 60s`（见
  // `ShelfBookCard` 的 `Guide`）。这个字段原先写的是**当天** 10:00Z，于是这条
  // 夹具带着一颗时间炸弹：在时间走到 10:00Z 之前，`Date.now() - created_at`
  // 是**负数**，小于 60s 成立，用例一直是绿的；一过 10:00Z 就永久变红，
  // 而且失败信息看起来像业务代码坏了（"找不到『导读生成中…』"），
  // 排查方向会被带偏。
  //
  // 需要"刚加进来"的用例，请在**用例里**用 `new Date().toISOString()` 现算，
  // 不要在这里写死——整套测试并行跑可以超过 60 秒，模块加载时算的照样会过期。
  created_at: '2026-01-01T00:00:00+00:00',
  updated_at: '2026-01-01T00:00:00+00:00',
}

const EMPTY = { total: 0, counts: {}, books: [] }

/** 把若干本书包成 `/api/shelf` 的响应。

参数写成 ``ShelfBook[]`` 而不是 ``typeof BOOK[]``：后者会把 ``status`` 钉死成
``"wish"`` 这个字面量（BOOK 里带 ``as const``），于是下面想造一本"读过"的书就会
报 ``"done" 不能赋给 "wish"``——一句看着像业务 bug、其实是夹具自缚的错。
*/
function shelfOf(books: ShelfBook[]) {
  return {
    total: books.length,
    counts: books.reduce<Record<string, number>>((acc, book) => {
      acc[book.status] = (acc[book.status] ?? 0) + 1
      return acc
    }, {}),
    books,
  }
}

function renderShelf() {
  return render(
    <I18nProvider>
      <MemoryRouter>
        <ShelfPage />
      </MemoryRouter>
    </I18nProvider>,
  )
}

/** 检索一次并等结果落下来。 */
async function searchFor(title: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('书名'), title)
  await user.click(screen.getByRole('button', { name: '联网检索' }))
  return user
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.listShelf.mockResolvedValue(EMPTY)
})

describe('我的书架', () => {
  it('空书架给一句解释和一个去处', async () => {
    renderShelf()
    expect(await screen.findByText('书架还是空的')).toBeInTheDocument()
    expect(screen.getByText('在上面输入书名，从检索结果里挑一本加进来。')).toBeInTheDocument()
  })

  it('列出书名、作者与阅读状态', async () => {
    mockedApi.listShelf.mockResolvedValue(shelfOf([BOOK]))
    renderShelf()

    expect(await screen.findByRole('heading', { name: '活着' })).toBeInTheDocument()
    expect(screen.getByText('余华 · 2012')).toBeInTheDocument()
    // 三个状态药丸都在，当前状态是"想读"
    expect(screen.getByRole('button', { name: '改为「想读」' })).toHaveAttribute(
      'class',
      expect.stringContaining('cinnabar'),
    )
  })

  it('按状态筛选，本地过滤不重新请求', async () => {
    mockedApi.listShelf.mockResolvedValue(
      shelfOf([BOOK, { ...BOOK, id: 8, title: '三体', status: 'done' as const }]),
    )
    renderShelf()
    await screen.findByRole('heading', { name: '活着' })
    const callsAfterLoad = mockedApi.listShelf.mock.calls.length

    const user = userEvent.setup()
    // 筛选药丸的可访问名以「读过」开头；每张卡片上那个状态药丸的名字是
    // 「改为「读过」」，两者靠这个前缀区分开。
    await user.click(screen.getByRole('button', { name: /^读过/ }))

    expect(screen.getByRole('heading', { name: '三体' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '活着' })).not.toBeInTheDocument()
    // 筛选是纯本地的：多打一次后端只会让切来切去发顿
    expect(mockedApi.listShelf.mock.calls.length).toBe(callsAfterLoad)
  })
})

describe('联网检索加书', () => {
  it('输入书名检索，把候选列出来', async () => {
    mockedApi.searchBooks.mockResolvedValue({ results: [CANDIDATE], error: '' })
    renderShelf()
    await searchFor('活着')

    expect(await screen.findByText('活着')).toBeInTheDocument()
    expect(screen.getByText('余华 · 2012')).toBeInTheDocument()
    expect(mockedApi.searchBooks).toHaveBeenCalledWith('活着', '')
  })

  it('检索可以带上作者', async () => {
    mockedApi.searchBooks.mockResolvedValue({ results: [CANDIDATE], error: '' })
    renderShelf()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('书名'), '活着')
    await user.type(screen.getByLabelText('作者（可留空）'), '余华')
    await user.click(screen.getByRole('button', { name: '联网检索' }))

    await waitFor(() => expect(mockedApi.searchBooks).toHaveBeenCalledWith('活着', '余华'))
  })

  it('搜不到时说的是"没有这本书"，并给一条改法', async () => {
    mockedApi.searchBooks.mockResolvedValue({ results: [], error: '' })
    renderShelf()
    await searchFor('不存在的书')

    expect(await screen.findByText('没有找到这本书')).toBeInTheDocument()
    expect(screen.getByText('换个说法试试：只写书名，或补上作者。')).toBeInTheDocument()
  })

  it('上游限流这类失败走 error 字段，且不算"没有这本书"', async () => {
    mockedApi.searchBooks.mockResolvedValue({
      results: [],
      error: '检索服务请求过于频繁，请稍后再试',
    })
    renderShelf()
    await searchFor('活着')

    expect(await screen.findByRole('alert')).toHaveTextContent('检索服务请求过于频繁')
    expect(screen.queryByText('没有找到这本书')).not.toBeInTheDocument()
  })

  it('点"加入书架"把选中的候选原样回传', async () => {
    mockedApi.searchBooks.mockResolvedValue({ results: [CANDIDATE], error: '' })
    mockedApi.addShelfBook.mockResolvedValue(BOOK)
    renderShelf()
    const user = await searchFor('活着')

    await user.click(await screen.findByRole('button', { name: '加入书架' }))

    await waitFor(() => expect(mockedApi.addShelfBook).toHaveBeenCalledWith(CANDIDATE))
    expect(await screen.findByText('《活着》已加入，导读正在后台生成。')).toBeInTheDocument()
  })

  it('已经在书架上的书，候选里标出来并禁用', async () => {
    // 同一本书搜两次很常见；不禁用的话用户会点第二次，
    // 然后收到一个"已经在书架里了"的错误——本该是显而易见的。
    mockedApi.listShelf.mockResolvedValue(shelfOf([BOOK]))
    mockedApi.searchBooks.mockResolvedValue({ results: [CANDIDATE], error: '' })
    renderShelf()
    await screen.findByRole('heading', { name: '活着' })
    await searchFor('活着')

    const button = await screen.findByRole('button', { name: '已在书架里' })
    expect(button).toBeDisabled()
  })

  it('加书失败时把原因显示出来', async () => {
    mockedApi.searchBooks.mockResolvedValue({ results: [CANDIDATE], error: '' })
    mockedApi.addShelfBook.mockRejectedValue(new Error('这本书已经在你的书架里了'))
    renderShelf()
    const user = await searchFor('活着')

    await user.click(await screen.findByRole('button', { name: '加入书架' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('这本书已经在你的书架里了')
  })
})

describe('书架上的操作', () => {
  it('改阅读状态只换那一条，不重拉整页', async () => {
    mockedApi.listShelf.mockResolvedValue(shelfOf([BOOK]))
    mockedApi.updateShelfBook.mockResolvedValue({ ...BOOK, status: 'reading' })
    renderShelf()
    await screen.findByRole('heading', { name: '活着' })
    const callsAfterLoad = mockedApi.listShelf.mock.calls.length

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '改为「在读」' }))

    await waitFor(() => expect(mockedApi.updateShelfBook).toHaveBeenCalledWith(7, { status: 'reading' }))
    expect(mockedApi.listShelf.mock.calls.length).toBe(callsAfterLoad)
  })

  it('申请公开之后显示"待审核"', async () => {
    mockedApi.listShelf.mockResolvedValue(shelfOf([BOOK]))
    mockedApi.submitShelfBook.mockResolvedValue({ ...BOOK, visibility: 'pending' })
    renderShelf()
    await screen.findByRole('heading', { name: '活着' })

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '申请公开' }))

    expect(await screen.findByText('待审核')).toBeInTheDocument()
    // 已提交的书不该再显示"申请公开"——再点一次没有任何意义
    expect(screen.queryByRole('button', { name: '申请公开' })).not.toBeInTheDocument()
  })

  it('待审核时可以撤回', async () => {
    mockedApi.listShelf.mockResolvedValue(
      shelfOf([{ ...BOOK, visibility: 'pending' as const }]),
    )
    mockedApi.cancelShelfBook.mockResolvedValue(BOOK)
    renderShelf()
    await screen.findByRole('heading', { name: '活着' })

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '撤回申请' }))

    await waitFor(() => expect(mockedApi.cancelShelfBook).toHaveBeenCalledWith(7))
    expect(await screen.findByRole('button', { name: '申请公开' })).toBeInTheDocument()
  })

  it('被驳回的书把原因摆出来，并且还能再申请一次', async () => {
    mockedApi.listShelf.mockResolvedValue(
      shelfOf([
        { ...BOOK, visibility: 'rejected' as const, review_note: '与现有书目重复' },
      ]),
    )
    renderShelf()

    expect(await screen.findByText('驳回原因：与现有书目重复')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '申请公开' })).toBeInTheDocument()
  })

  it('删除要先就地确认一次', async () => {
    // 用 confirm() 在嵌入式预览里会被静默拦掉，表现是"点了没反应"。
    // 这条断言同时守住了"不用原生弹窗"这个决定。
    mockedApi.listShelf.mockResolvedValue(shelfOf([BOOK]))
    mockedApi.removeShelfBook.mockResolvedValue({ ok: true })
    renderShelf()
    await screen.findByRole('heading', { name: '活着' })

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '移出书架' }))
    expect(mockedApi.removeShelfBook).not.toHaveBeenCalled()

    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: '确认删除' }))
    await waitFor(() => expect(mockedApi.removeShelfBook).toHaveBeenCalledWith(7))
  })

  it('导读默认收起，展开才渲染正文', async () => {
    mockedApi.listShelf.mockResolvedValue(shelfOf([BOOK]))
    renderShelf()
    await screen.findByRole('heading', { name: '活着' })

    expect(screen.queryByText('这本书在讲什么')).not.toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /展开导读/ }))
    expect(await screen.findByText('这本书在讲什么')).toBeInTheDocument()
  })

  it('导读还没生成时说的是"生成中"，不是"没有导读"', async () => {
    // 两者原因完全不同：一个是等待，一个是失败。共用一句话，
    // 用户会以为加书没成功。
    //
    // `created_at` 在**用例里**现算：组件判"是不是刚加的"用的是
    // `Date.now() - created_at < 60s`，夹具里写死某个时刻的话，这套测试
    // 跑到第 61 秒就开始红（整套并行时确实跑得那么久）。
    mockedApi.listShelf.mockResolvedValue(
      shelfOf([
        { ...BOOK, guide: '', has_guide: false, created_at: new Date().toISOString() },
      ]),
    )
    renderShelf()

    expect(await screen.findByText('导读生成中…')).toBeInTheDocument()
    expect(screen.queryByText('这本书还没有导读')).not.toBeInTheDocument()
  })

  it('加完很久还没导读，说的是"还没有导读"而不是一直"生成中"', async () => {
    // 另一支。以前只测了"生成中"那一支，于是那边挂了也看不出是哪一支的问题；
    // 而且这一支本身是必要的——生成失败的书不能永远显示"在等"。
    mockedApi.listShelf.mockResolvedValue(
      shelfOf([
        { ...BOOK, guide: '', has_guide: false, created_at: '2026-01-01T00:00:00+00:00' },
      ]),
    )
    renderShelf()

    expect(await screen.findByText('这本书还没有导读')).toBeInTheDocument()
    expect(screen.queryByText('导读生成中…')).not.toBeInTheDocument()
  })
})

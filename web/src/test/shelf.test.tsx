import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { api } from '../api/client'
import type { ShelfBook } from '../api/types'
import ShelfPage from '../features/shelf/ShelfPage'
import { GUIDE_POLL_MAX, GUIDE_POLL_MS } from '../features/shelf/constants'
import { I18nProvider } from '../i18n'

vi.mock('../api/client', async (importOriginal) => {
  // 真实导出照单全收——只把 `api` 换成假的。手写一份导出清单是脆的：
  // 模块新增一个导出（本轮的 `peek` 就是），十几个测试文件会一起挂，
  // 而报出来的错（"mock 里没有 peek"）跟这些用例要测的事毫无关系。
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: {
      listShelf: vi.fn(),
      searchBooks: vi.fn(),
      addShelfBook: vi.fn(),
      updateShelfBook: vi.fn(),
      removeShelfBook: vi.fn(),
      submitShelfBook: vi.fn(),
      cancelShelfBook: vi.fn(),
      regenerateShelfGuide: vi.fn(),
    },
  }
})

const mockedApi = vi.mocked(api)

const CANDIDATE = {
  title: '活着',
  author: '余华',
  year: '2012',
  cover_url: '',
  source_key: '834464',
  source: 'weread',
  summary: '一个人和他命运之间的友情。',
  subjects: [],
}

const BOOK = {
  id: 7,
  title: '活着',
  author: '余华',
  year: '2012',
  cover_url: '',
  source_key: '834464',
  summary: '',
  subjects: [],
  guide: '## 这本书在讲什么\n\n一个人和他命运之间的友情。',
  has_guide: true,
  guide_error: '',
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
    mockedApi.searchBooks.mockResolvedValue({ results: [CANDIDATE], error: '', unavailable: false })
    renderShelf()
    await searchFor('活着')

    expect(await screen.findByText('活着')).toBeInTheDocument()
    expect(screen.getByText('余华 · 2012')).toBeInTheDocument()
    expect(mockedApi.searchBooks).toHaveBeenCalledWith('活着', '')
  })

  it('检索可以带上作者', async () => {
    mockedApi.searchBooks.mockResolvedValue({ results: [CANDIDATE], error: '', unavailable: false })
    renderShelf()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('书名'), '活着')
    await user.type(screen.getByLabelText('作者（可留空）'), '余华')
    await user.click(screen.getByRole('button', { name: '联网检索' }))

    await waitFor(() => expect(mockedApi.searchBooks).toHaveBeenCalledWith('活着', '余华'))
  })

  it('搜不到时说的是"没有这本书"，并给一条改法', async () => {
    mockedApi.searchBooks.mockResolvedValue({ results: [], error: '', unavailable: false })
    renderShelf()
    await searchFor('不存在的书')

    expect(await screen.findByText('没有找到这本书')).toBeInTheDocument()
    expect(screen.getByText('换个说法试试：只写书名，或补上作者。')).toBeInTheDocument()
  })

  it('上游限流这类失败走 error 字段，且不算"没有这本书"', async () => {
    mockedApi.searchBooks.mockResolvedValue({
      results: [],
      error: '检索服务请求过于频繁，请稍后再试',
      unavailable: false,
    })
    renderShelf()
    await searchFor('活着')

    expect(await screen.findByRole('alert')).toHaveTextContent('检索服务请求过于频繁')
    expect(screen.queryByText('没有找到这本书')).not.toBeInTheDocument()
  })

  it('所有书源都没连上时如实报原因，且**只发一次请求**', async () => {
    // 这条是这次改动的判据。以前后端回 `unavailable` 之后，前端会再往
    // openlibrary.org 打一次"浏览器直连"——而现役书源（微信读书 / 豆瓣）都不发
    // CORS 头，那次请求注定失败，唯一的效果是让用户**再**多等 20 秒，然后收到
    // 一句"浏览器与服务器两条路都没通"。
    mockedApi.searchBooks.mockResolvedValue({
      results: [],
      error: '无法连接检索服务：timed out',
      unavailable: true,
    })
    renderShelf()
    await searchFor('活着')

    expect(await screen.findByRole('alert')).toHaveTextContent('无法连接检索服务')
    expect(mockedApi.searchBooks).toHaveBeenCalledTimes(1)
    // 连不上**不能**说成"世上没这本书"——那会让用户去改书名而不是重试
    expect(screen.queryByText('没有找到这本书')).not.toBeInTheDocument()
  })

  it('后端整个请求都失败时，也要说点什么而不是静默', async () => {
    mockedApi.searchBooks.mockRejectedValue(new Error('Failed to fetch'))
    renderShelf()
    await searchFor('活着')

    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to fetch')
  })

  it('点"加入书架"把选中的候选原样回传', async () => {
    mockedApi.searchBooks.mockResolvedValue({ results: [CANDIDATE], error: '', unavailable: false })
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
    mockedApi.searchBooks.mockResolvedValue({ results: [CANDIDATE], error: '', unavailable: false })
    renderShelf()
    await screen.findByRole('heading', { name: '活着' })
    await searchFor('活着')

    const button = await screen.findByRole('button', { name: '已在书架里' })
    expect(button).toBeDisabled()
  })

  it('加书失败时把原因显示出来', async () => {
    mockedApi.searchBooks.mockResolvedValue({ results: [CANDIDATE], error: '', unavailable: false })
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

/** 一本加进来很久、但导读是空的书。时间取**明确在过去**的固定时刻：
 *  `created_at` 落在 60 秒内的话，卡片会走"生成中"那一支（见夹具上的说明）。 */
const NO_GUIDE: ShelfBook = {
  ...BOOK,
  guide: '',
  has_guide: false,
  guide_error: '',
  created_at: '2026-01-01T00:00:00+00:00',
}

describe('导读就是这本书的正文', () => {
  // 报障的原话是"检索出来了但是不给读，我点不了"。书架里的书没有正文
  // （联网检索只拿得到书名、作者、封面、简介），导读是唯一能读的东西——
  // 所以它必须是可点的，不可点时也必须说清楚为什么。

  it('有导读时书名可点，点开就是正文', async () => {
    mockedApi.listShelf.mockResolvedValue(shelfOf([BOOK]))
    renderShelf()
    await screen.findByRole('heading', { name: '活着' })

    const user = userEvent.setup()
    // 卡片上那个可访问名就是书名的按钮，只能是标题本身——换句话说，
    // 用户看到"活着"这两个字就能点
    await user.click(screen.getByRole('button', { name: '活着' }))
    expect(await screen.findByText('这本书在讲什么')).toBeInTheDocument()
  })

  it('没有导读时书名保持纯文本，不给一个点了没反应的按钮', async () => {
    mockedApi.listShelf.mockResolvedValue(shelfOf([NO_GUIDE]))
    renderShelf()
    await screen.findByRole('heading', { name: '活着' })

    expect(screen.queryByRole('button', { name: '活着' })).not.toBeInTheDocument()
    // 标题本身还在（筛选用例、读屏都按 heading 找它）
    expect(screen.getByRole('heading', { name: '活着' })).toBeInTheDocument()
  })

  it('没导读时说出"这本书本来就没有正文"——否则用户以为是点不开', async () => {
    mockedApi.listShelf.mockResolvedValue(shelfOf([NO_GUIDE]))
    renderShelf()

    expect(await screen.findByText(/正文不在库里/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '生成导读' })).toBeInTheDocument()
  })

  it('刚加进来就已经失败了：直接说失败，不让人对着"生成中"多等一分钟', async () => {
    // "刚加进来"那条时间判据是个猜测（加进来不到 60 秒就当在生成）。一旦
    // `guide_error` 有内容，就不用猜了——这一次已经有结果，只是结果是失败。
    // 此时还挂着"生成中"，用户会继续等，而正确动作是点一下重试。
    mockedApi.listShelf.mockResolvedValue(
      shelfOf([
        {
          ...NO_GUIDE,
          guide_error: '模型调用失败：timed out',
          created_at: new Date().toISOString(),
        },
      ]),
    )
    renderShelf()

    expect(await screen.findByText(/模型调用失败/)).toBeInTheDocument()
    expect(screen.queryByText('导读生成中…')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新生成导读' })).toBeInTheDocument()
  })

  it('生成失败过：把原因摆出来，并把"生成"改成"重新生成"', async () => {
    // 原先"失败"与"没试过"共用「这本书还没有导读」，用户既不知道出了什么事，
    // 也没有重试的落脚点——而失败是永久的：后台任务只跑一次，不会自己重来。
    mockedApi.listShelf.mockResolvedValue(
      shelfOf([{ ...NO_GUIDE, guide_error: '模型调用失败：timed out（已尝试：kimi-k3）' }]),
    )
    renderShelf()

    expect(await screen.findByText(/模型调用失败/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新生成导读' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '生成导读' })).not.toBeInTheDocument()
  })

  it('点"生成导读"立刻转成"生成中"，跑完再换成能读的导读', async () => {
    // "点了没反应"是这次报障的另一半。重新生成至少要十几秒才出结果，
    // 中间那一段必须自己说出来，否则用户只会再点一次、或者以为按钮坏了。
    mockedApi.listShelf
      .mockResolvedValueOnce(shelfOf([NO_GUIDE]))
      .mockResolvedValue(shelfOf([BOOK]))

    let release: (book: ShelfBook) => void = () => {}
    mockedApi.regenerateShelfGuide.mockReturnValue(
      new Promise<ShelfBook>(resolve => {
        release = resolve
      }),
    )

    renderShelf()
    await screen.findByText('这本书还没有导读')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '生成导读' }))

    expect(await screen.findByText('导读生成中…')).toBeInTheDocument()
    expect(screen.queryByText('这本书还没有导读')).not.toBeInTheDocument()

    release({ ...NO_GUIDE, guide_error: '' })

    // 生成完就换成"展开导读"——书名这时也能点了
    expect(await screen.findByRole('button', { name: /展开导读/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '活着' })).toBeInTheDocument()
  })

  it('重新生成失败时把原因显示在卡片上，不静默', async () => {
    mockedApi.listShelf.mockResolvedValue(shelfOf([NO_GUIDE]))
    mockedApi.regenerateShelfGuide.mockRejectedValue(new Error('书架里没有这本书'))
    renderShelf()
    await screen.findByText('这本书还没有导读')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '生成导读' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('书架里没有这本书')
  })

  it('导读没好时，轮询会一轮一轮地来，直到预算用完', async () => {
    // 这一条盯的是一个**静默失效**：轮询 effect 的依赖里有 `pendingGuides`，
    // 而它是个**数字**——`load()` 回来之后往往还是同一个值（1 还是 1），依赖
    // 没变 effect 就不会重跑，下一支定时器排不出来。于是"最多看 8 次"实际只
    // 发生了 1 次：第 4 秒看一眼，没等到就永远停在那一刻。实测过：点了重新
    // 生成之后浏览器只发出 1 个轮询请求，之后 42 秒一片安静，界面一直挂着
    // "导读生成中…"，而书架上其实早就有导读或失败原因了。
    //
    // 两个注意点（都是踩过的）：
    //   · React 的提交落在真实宏任务里，一次 `advanceTimersByTimeAsync` 只推得动
    //     一支定时器——所以要**一轮一轮地推**，不能一把推 48 秒；
    //   · 假定时器下别用 `findBy*` / `waitFor`，它们靠真实轮询，会一直等到超时。
    vi.useFakeTimers()
    try {
      mockedApi.listShelf.mockResolvedValue(shelfOf([NO_GUIDE]))
      renderShelf()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(mockedApi.listShelf).toHaveBeenCalledTimes(1) // 首次加载

      for (let round = 1; round <= GUIDE_POLL_MAX; round += 1) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(GUIDE_POLL_MS)
        })
      }
      // **恰好**"首次 + GUIDE_POLL_MAX 次"。这一条能成立，就说明那 8 支定时器
      // 是一支接一支真排出来的——修的正是"只排得出第一支"。
      expect(mockedApi.listShelf).toHaveBeenCalledTimes(1 + GUIDE_POLL_MAX)

      // 预算用完就真的停：再多推几轮也不该继续发请求
      for (let extra = 0; extra < 3; extra += 1) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(GUIDE_POLL_MS)
        })
      }
      expect(mockedApi.listShelf).toHaveBeenCalledTimes(1 + GUIDE_POLL_MAX)
    } finally {
      vi.useRealTimers()
    }
  })

  it('重新生成之后，会一直等到有结论为止，不会永远停在"生成中"', async () => {
    // 上一条盯的是"轮询有没有继续"，这一条盯的是**用户看到的那一面**：
    // 点了重新生成之后，只要后端给出了结论（这里仍是失败），卡片的"生成中"
    // 必须让位给原因。少了它，用户就会对着骨架屏等一辈子。
    vi.useFakeTimers()
    try {
      const failed = shelfOf([{ ...NO_GUIDE, guide_error: '模型没有答复（超时）' }])
      const cleared = shelfOf([NO_GUIDE])
      // 节奏照着真实后端来：失败**不是**下一次拉取就有结果的——本机实测约
      // 10 秒，也就是要走过好几轮轮询。若只给"下一轮就出结果"，
      // 那个只排得出一支定时器的毛病照样能混过去（一次轮询刚好够用）。
      mockedApi.listShelf
        .mockResolvedValueOnce(failed) // 首屏：这本书失败过
        .mockResolvedValueOnce(cleared) // 点重试后立刻拉：后端把旧原因清了
        .mockResolvedValueOnce(cleared) // 第 1 轮轮询：还没出结果
        .mockResolvedValueOnce(cleared) // 第 2 轮
        .mockResolvedValue(failed) // 第 3 轮：这一次也失败了
      mockedApi.regenerateShelfGuide.mockResolvedValue(NO_GUIDE)

      renderShelf()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(screen.getByText(/模型没有答复/)).toBeInTheDocument()

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '重新生成导读' }))
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(screen.getByText('导读生成中…')).toBeInTheDocument()

      // 走过几轮轮询，结论就该回来
      for (let round = 0; round < 3; round += 1) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(GUIDE_POLL_MS)
        })
      }
      expect(screen.getByText(/模型没有答复/)).toBeInTheDocument()
      expect(screen.queryByText('导读生成中…')).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })
})

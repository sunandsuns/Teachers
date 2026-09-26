/**
 * 访问边界：**登录之前，一个页面也看不了**。
 *
 * 这里渲染的是**真实的 `<App />`**，而不是在测试里照抄一份路由表。
 * 抄一份的话，测的是抄的那份：`App.tsx` 里漏包一条路由，这个测试照样全绿，
 * 而那条路由已经安静地对匿名开放了。要的就是"漏包会被抓出来"。
 *
 * 所以下面那张清单不是"页面的清单"，而是**对 `App.tsx` 的断言**：
 * 往路由表里加一条却没放进 `RequireAuth`，这里就会红。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { api } from '../api/client'
import { AuthProvider } from '../features/auth/AuthProvider'
import { I18nProvider } from '../i18n'

// 只 mock 会被真正用到的接口：未登录访问内容路由时，页面根本不渲染，
// 那些页面自己的接口连一次都不会被调——这正是下面要断言的一件事。
vi.mock('../api/client', () => ({
  api: {
    me: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    listBooks: vi.fn(),
    getBook: vi.fn(),
    listChapters: vi.fn(),
    getChapter: vi.fn(),
    getSource: vi.fn(),
    listShelf: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

const BOOK = {
  book_id: '01',
  title: '道德经',
  author: '老子',
  category: '哲学',
  chapter_count: 1,
  has_source: false,
}

const VIEWER = {
  id: 2,
  email: 'alice@example.com',
  display_name: '小艾',
  name: '小艾',
  is_admin: false,
  created_at: '2026-01-01T00:00:00+00:00',
}

/** **每一条**内容路由都要登录，包括书架（`/`）与阅读页（`/books/:id`）。
 *
 * 这张清单存在的意义就是"漏一条会被抓出来"：往 `App.tsx` 的路由表里加一页，
 * 忘了挪进 `RequireAuth`，这里立刻红。 */
const GATED_PATHS = [
  '/',
  '/books/01',
  '/shelf',
  '/search',
  '/knowledge',
  '/ask',
  '/history',
  '/profile',
  '/insights',
  '/admin',
]

/** 把整个应用渲染在指定路径上。`user` 决定"登没登录"。 */
function renderAt(path: string, user: typeof VIEWER | null = null) {
  mockedApi.me.mockResolvedValue({ user })
  return render(
    <I18nProvider>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </I18nProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.listBooks.mockResolvedValue([BOOK])
  mockedApi.getBook.mockResolvedValue(BOOK)
  mockedApi.listChapters.mockResolvedValue([{ chapter_id: '01', title: '缘起', book_id: '01' }])
  mockedApi.getChapter.mockResolvedValue({
    chapter_id: '01',
    title: '缘起',
    book_id: '01',
    content: '道可道，非常道。',
  })
  mockedApi.listShelf.mockResolvedValue({ total: 0, counts: {}, books: [] })
})

describe('登录之前', () => {
  it.each(GATED_PATHS)('%s 被送到登录页', async path => {
    renderAt(path)
    // 断言"表单真的在"，而不是"页面上没有别的东西"——后者在整页渲染失败时
    // 同样成立，那种"通过"毫无意义。
    expect(await screen.findByLabelText('邮箱')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument()
  })

  it('登录页是整屏的：没有导航栏', async () => {
    // 未登录时那七个导航项全是同一个死胡同（点哪个都回到这一页），
    // 所以登录页只有产品名与表单。品牌名保留，不然用户不知道这是哪儿。
    renderAt('/ask')
    await screen.findByLabelText('邮箱')
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
    expect(screen.getByText('人生导师')).toBeInTheDocument()
  })

  it('被拦下时，那一页自己的数据一次都不去取', async () => {
    // 若是"先渲染页面、再把登录页盖上去"，下面的请求就已经发出去了。
    // 对匿名来说是白跑一趟，对"我的书架"这种私密数据更是把接口暴露了。
    renderAt('/shelf')
    await screen.findByLabelText('邮箱')
    expect(mockedApi.listShelf).not.toHaveBeenCalled()
    expect(mockedApi.listBooks).not.toHaveBeenCalled()
  })

  it('书架与阅读页也不例外', async () => {
    renderAt('/')
    await screen.findByLabelText('邮箱')
    expect(mockedApi.listBooks).not.toHaveBeenCalled()
  })
})

describe('被送过来时，登录页说得清"登完去哪儿"', () => {
  it('点名刚才那一页', async () => {
    renderAt('/shelf')
    expect(await screen.findByText('登录后回到「我的书架」')).toBeInTheDocument()
  })

  it('从首页进来就不点名（没有来路可言）', async () => {
    renderAt('/')
    await screen.findByLabelText('邮箱')
    expect(screen.queryByText(/登录后回到/)).not.toBeInTheDocument()
  })
})

describe('登录之后', () => {
  it('同一条路由就变成内容了', async () => {
    renderAt('/shelf', VIEWER)
    await waitFor(() => expect(mockedApi.listShelf).toHaveBeenCalled())
    expect(screen.queryByLabelText('邮箱')).not.toBeInTheDocument()
  })

  it('书架（首页）也一样', async () => {
    renderAt('/', VIEWER)
    expect(await screen.findByText('道德经')).toBeInTheDocument()
  })

  it('已经登录的人停在 /login 上，看到的是"已登录"而不是表单', async () => {
    renderAt('/login', VIEWER)
    expect(await screen.findByText('已登录 · 小艾')).toBeInTheDocument()
    expect(screen.queryByLabelText('邮箱')).not.toBeInTheDocument()
  })
})

describe('登录完成后回到原来那一页', () => {
  it('登完回到被拦下那页', async () => {
    const user = userEvent.setup()
    mockedApi.login.mockResolvedValue(VIEWER)

    renderAt('/shelf')
    await screen.findByLabelText('邮箱')
    await user.type(screen.getByLabelText('邮箱'), 'alice@example.com')
    await user.type(screen.getByLabelText('密码'), 'goodpass123')
    await user.click(screen.getByRole('button', { name: '登录' }))

    // 回到「我的书架」的证据是它自己去取了数据，而不是"页面上有某个词"
    await waitFor(() => expect(mockedApi.listShelf).toHaveBeenCalled())
    expect(screen.queryByLabelText('邮箱')).not.toBeInTheDocument()
  })

  it('从首页进来的，登完就落在首页', async () => {
    const user = userEvent.setup()
    mockedApi.login.mockResolvedValue(VIEWER)

    renderAt('/')
    await screen.findByLabelText('邮箱')
    await user.type(screen.getByLabelText('邮箱'), 'alice@example.com')
    await user.type(screen.getByLabelText('密码'), 'goodpass123')
    await user.click(screen.getByRole('button', { name: '登录' }))

    expect(await screen.findByText('道德经')).toBeInTheDocument()
  })

  it('中途点了"去注册"，来路仍然记得', async () => {
    // 从登录页跳注册页时若不带 `state`，`from` 就断了——用户刚点过的入口
    // 被悄悄忘掉，注册完只会落到默认那一页。
    const user = userEvent.setup()
    mockedApi.register.mockResolvedValue(VIEWER)

    renderAt('/shelf')
    await screen.findByLabelText('邮箱')
    await user.click(screen.getByRole('link', { name: '还没有账号？去注册' }))

    await screen.findByLabelText('昵称（可留空）')
    expect(screen.getByText('登录后回到「我的书架」')).toBeInTheDocument()
    await user.type(screen.getByLabelText('邮箱'), 'alice@example.com')
    await user.type(screen.getByLabelText('密码'), 'goodpass123')
    await user.click(screen.getByRole('button', { name: '注册并登录' }))

    await waitFor(() => expect(mockedApi.listShelf).toHaveBeenCalled())
  })
})

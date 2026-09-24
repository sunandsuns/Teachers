/**
 * 访问边界：哪些路由对匿名开放，哪些要登录。
 *
 * 这里渲染的是**真实的 `<App />`**，而不是在测试里照抄一份路由表。
 * 抄一份的话，测的是抄的那份：`App.tsx` 里漏包一条路由，这个测试照样全绿，
 * 而那条路由已经安静地对匿名开放了。要的就是"漏包会被抓出来"。
 *
 * 所以下面两张清单不是"页面的清单"，而是**对 `App.tsx` 的断言**：
 * 往路由表里加一条却没放进 `RequireAuth`，或者把某条挪了出来，这里就会红。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { api } from '../api/client'
import { AuthProvider } from '../features/auth/AuthProvider'
import { I18nProvider } from '../i18n'

// 只 mock 会被真正用到的接口：匿名访问受保护路由时，页面根本不渲染，
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

/** 匿名也该看得见的：公共书架与阅读页。
 *
 * 门只开在这两处，是因为书架是这套产品的门面：匿名用户能翻书目、能点开
 * 读正文，才知道这里有什么。反过来若把阅读页也拦掉，匿名看到一堆点不开的
 * 书名，书架就成了死胡同。 */
const PUBLIC_PATHS = ['/', '/books/01']

/** 其余全部要登录。 */
const GATED_PATHS = [
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

describe('匿名能去的地方', () => {
  it.each(PUBLIC_PATHS)('%s 不拦', async path => {
    renderAt(path)
    await waitFor(() => expect(mockedApi.me).toHaveBeenCalled())

    // 只断言"没有登录门"是不够的：整页渲染失败时同样"没有门"。
    // 所以还要看到这一页自己的内容（或它自己的请求真的发出去了）。
    expect(screen.queryByText('需要先登录')).not.toBeInTheDocument()
    if (path === '/') {
      expect(await screen.findByText('道德经')).toBeInTheDocument()
    } else {
      await waitFor(() => expect(mockedApi.getBook).toHaveBeenCalledWith('01'))
    }
  })
})

describe('匿名不该去的地方', () => {
  it.each(GATED_PATHS)('%s 拦下来，并给出去登录的出口', async path => {
    renderAt(path)
    expect(await screen.findByText('需要先登录')).toBeInTheDocument()
    // 只说"不能进"不给出路，用户就卡住了
    expect(screen.getByRole('button', { name: '去登录' })).toBeInTheDocument()
  })

  it('被拦下的页面连数据都不去取（门是真挡住，不是盖在上面）', async () => {
    // 若是"先渲染页面、再拿门盖住"，下面的请求就已经发出去了——
    // 对匿名来说是白跑一趟，对"我的书架"这种私密数据更是把接口暴露了。
    renderAt('/shelf')
    await waitFor(() => expect(mockedApi.me).toHaveBeenCalled())
    expect(screen.getByText('需要先登录')).toBeInTheDocument()
    expect(mockedApi.listShelf).not.toHaveBeenCalled()
  })
})

describe('登录之后', () => {
  it('同一条路由就变成内容了', async () => {
    renderAt('/shelf', VIEWER)
    await waitFor(() => expect(mockedApi.listShelf).toHaveBeenCalled())
    expect(screen.queryByText('需要先登录')).not.toBeInTheDocument()
  })
})

describe('登录完成后回到原来那一页', () => {
  it('从登录门进去，登完回到被拦下那页', async () => {
    const user = userEvent.setup()
    mockedApi.login.mockResolvedValue(VIEWER)

    renderAt('/shelf')
    await user.click(await screen.findByRole('button', { name: '去登录' }))

    await screen.findByLabelText('邮箱')
    await user.type(screen.getByLabelText('邮箱'), 'alice@example.com')
    await user.type(screen.getByLabelText('密码'), 'goodpass123')
    await user.click(screen.getByRole('button', { name: '登录' }))

    // 回到「我的书架」的证据是它自己去取了数据，而不是"页面上有某个词"
    await waitFor(() => expect(mockedApi.listShelf).toHaveBeenCalled())
    expect(screen.queryByText('需要先登录')).not.toBeInTheDocument()
  })

  it('中途点了"去注册"，来路仍然记得', async () => {
    // 从登录页跳注册页时若不带 `state`，`from` 就断了——用户刚点过的入口
    // 被悄悄忘掉，注册完只会落到默认那一页。
    const user = userEvent.setup()
    mockedApi.register.mockResolvedValue(VIEWER)

    renderAt('/shelf')
    await user.click(await screen.findByRole('button', { name: '去登录' }))
    await user.click(await screen.findByRole('link', { name: '还没有账号？去注册' }))

    await screen.findByLabelText('昵称（可留空）')
    await user.type(screen.getByLabelText('邮箱'), 'alice@example.com')
    await user.type(screen.getByLabelText('密码'), 'goodpass123')
    await user.click(screen.getByRole('button', { name: '注册并登录' }))

    await waitFor(() => expect(mockedApi.listShelf).toHaveBeenCalled())
    expect(screen.queryByText('需要先登录')).not.toBeInTheDocument()
  })
})

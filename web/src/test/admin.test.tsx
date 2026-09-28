import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { api, type AdminUserRow } from '../api/client'
import AdminPage from '../features/admin/AdminPage'
import { AuthProvider } from '../features/auth/AuthProvider'
import { I18nProvider } from '../i18n'

vi.mock('../api/client', async (importOriginal) => {
  // 真实导出照单全收——只把 `api` 换成假的。手写一份导出清单是脆的：
  // 模块新增一个导出（本轮的 `peek` 就是），十几个测试文件会一起挂，
  // 而报出来的错（"mock 里没有 peek"）跟这些用例要测的事毫无关系。
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: {
      me: vi.fn(),
      adminOverview: vi.fn(),
      adminUsers: vi.fn(),
      adminUserDetail: vi.fn(),
      adminReviewQueue: vi.fn(),
      adminReview: vi.fn(),
      adminPublicBooks: vi.fn(),
      adminRemovePublic: vi.fn(),
      adminTables: vi.fn(),
      adminTable: vi.fn(),
      adminUpdateRow: vi.fn(),
      adminInsertRow: vi.fn(),
      adminDeleteRow: vi.fn(),
      adminAudit: vi.fn(),
      adminSetAdmin: vi.fn(),
      adminResetPassword: vi.fn(),
      adminDeleteUser: vi.fn(),
    },
  }
})

const mockedApi = vi.mocked(api)

// `shelf_books` 是 AdminUserRow 的必填字段（用户列表要显示每人藏书数），
// 少了它 `adminSetAdmin` 这类返回 AdminUserRow 的 mock 会被 tsc 拦下。
const ADMIN = {
  id: 1,
  email: 'admin@test.local',
  display_name: '管理员',
  name: '管理员',
  is_admin: true,
  created_at: '2026-09-24T09:00:00+00:00',
  shelf_books: 0,
}

const PLAIN = { ...ADMIN, id: 5, email: 'bob@example.com', name: 'bob', is_admin: false }

const OVERVIEW = {
  users: 3,
  admins: 1,
  history: 42,
  history_today: 5,
  traits: 9,
  shelf_books: 7,
  shelf_books_today: 2,
  pending_review: 1,
  public_contributions: 0,
  sessions: 4,
  db_bytes: 2048,
  tables: 8,
  corpus_books: 15,
  corpus_chapters: 352,
  corpus_categories: ['儒家', '道家'],
  db_path: '/tmp/history.db',
  server_time: '2026-09-24T14:00:00+00:00',
}

const REVIEW_ROW = {
  id: 7,
  user_id: 5,
  user_email: 'bob@example.com',
  title: '活着',
  author: '余华',
  year: '2012',
  cover_url: '',
  summary: '一个人和他命运之间的友情。',
  subjects: ['Fiction'],
  guide: '',
  has_guide: false,
  visibility: 'pending' as const,
  review_note: '',
  created_at: '2026-09-24T10:00:00+00:00',
}

/** 一个用户的完整档案。字段与 `AdminUserDetail` 一一对应——少一个 tsc 就拦下。 */
const DETAIL = {
  user: PLAIN,
  stats: { history: 1, shelf_books: 1, traits: 1, public_books: 0 },
  history: [
    {
      id: 1,
      question: '我最近很焦虑',
      answer: '先说说是哪一件事让你睡不好。',
      model: 'kimi-k3',
      retrieved_count: 2,
      created_at: '2026-09-24T11:00:00+00:00',
    },
  ],
  books: [
    {
      id: 1,
      title: '活着',
      author: '余华',
      year: '2012',
      status: 'reading',
      visibility: 'private',
      review_note: '',
      created_at: '2026-09-24T10:30:00+00:00',
    },
  ],
  traits: [
    {
      id: 1,
      category: '性格',
      content: '做事偏谨慎',
      evidence: '我说我总要犹豫很久',
      confidence: 0.7,
      updated_at: '2026-09-24T10:40:00+00:00',
    },
  ],
}

function renderAdmin() {
  return render(
    <I18nProvider>
      <MemoryRouter>
        <AuthProvider>
          <AdminPage />
        </AuthProvider>
      </MemoryRouter>
    </I18nProvider>,
  )
}

/** 默认把后台那些接口都架好，各用例只覆盖自己关心的那一个。 */
function stubAdmin() {
  mockedApi.adminOverview.mockResolvedValue(OVERVIEW)
  mockedApi.adminUsers.mockResolvedValue([ADMIN, PLAIN])
  mockedApi.adminUserDetail.mockResolvedValue(DETAIL)
  mockedApi.adminReviewQueue.mockResolvedValue([])
  mockedApi.adminPublicBooks.mockResolvedValue([])
  mockedApi.adminTables.mockResolvedValue([{ name: 'users', rows: 3 }])
  mockedApi.adminTable.mockResolvedValue({ table: 'users', columns: [], total: 0, rows: [] })
  mockedApi.adminAudit.mockResolvedValue([])
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.me.mockResolvedValue({ user: ADMIN })
  stubAdmin()
})

describe('后台的权限边界', () => {
  it('未登录时这一页自己不说话——把人送去登录页由路由上的 `RequireAuth` 负责', async () => {
    // 门禁上移到路由层之后，`/admin` 未登录时根本走不到这一页：
    // `RequireAuth` 会先把人送到登录页。所以这里**什么都不渲染**，
    // 也不该把"你不是管理员"说成未登录——那句说错了，用户会去找管理员
    // 要权限，而他其实只需要登录。（"未登录进 /admin 会落到登录页"那条
    // 在 `route-access.test.tsx` 里，走的是真实的 `<App />` 路由表。）
    mockedApi.me.mockResolvedValue({ user: null })
    renderAdmin()

    await waitFor(() => expect(mockedApi.me).toHaveBeenCalled())
    // 未登录 = 不渲染任何东西：既没有"只对管理员开放"（那是说给已登录的
    // 普通用户听的），也没有后台自己的标题
    expect(screen.queryByText('这一页只对管理员开放')).not.toBeInTheDocument()
    // 同理也不该去问后台接口——没身份的人问也是 403
    expect(mockedApi.adminOverview).not.toHaveBeenCalled()
  })

  it('普通用户看到的是拒绝，且不去请求后台接口', async () => {
    mockedApi.me.mockResolvedValue({ user: PLAIN })
    renderAdmin()

    expect(await screen.findByText('这一页只对管理员开放')).toBeInTheDocument()
    // 明知会 403 还去问一遍，是白跑三趟
    expect(mockedApi.adminOverview).not.toHaveBeenCalled()
    expect(mockedApi.adminUsers).not.toHaveBeenCalled()
    expect(mockedApi.adminReviewQueue).not.toHaveBeenCalled()
  })

  it('管理员能看到总览', async () => {
    renderAdmin()
    expect(await screen.findByText('今日问答')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('15 部 · 352 章')).toBeInTheDocument()
    expect(screen.getByText('2.0 KB · 8 张表')).toBeInTheDocument()
  })
})

describe('新书审核', () => {
  it('待审队列为空时说清楚这里会出现什么', async () => {
    renderAdmin()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '新书审核' }))

    expect(await screen.findByText('没有待审的书')).toBeInTheDocument()
    expect(screen.getByText('用户申请公开的书会出现在这里。')).toBeInTheDocument()
  })

  it('列出待审的书与提交人', async () => {
    mockedApi.adminReviewQueue.mockResolvedValue([REVIEW_ROW])
    renderAdmin()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '新书审核' }))

    expect(await screen.findByRole('heading', { name: '活着' })).toBeInTheDocument()
    expect(screen.getByText('由 bob@example.com 提交')).toBeInTheDocument()
  })

  it('批准时把分类一并送出去', async () => {
    mockedApi.adminReviewQueue.mockResolvedValue([REVIEW_ROW])
    mockedApi.adminReview.mockResolvedValue({ ...REVIEW_ROW, visibility: 'public' })
    renderAdmin()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '新书审核' }))
    await screen.findByRole('heading', { name: '活着' })

    await user.type(screen.getByLabelText('归入分类（可留空）'), '文学')
    await user.click(screen.getByRole('button', { name: '批准公开' }))

    await waitFor(() =>
      expect(mockedApi.adminReview).toHaveBeenCalledWith(7, true, '', '文学'),
    )
  })

  it('驳回时把原因一起记下（作者看得到）', async () => {
    mockedApi.adminReviewQueue.mockResolvedValue([REVIEW_ROW])
    mockedApi.adminReview.mockResolvedValue({ ...REVIEW_ROW, visibility: 'rejected' })
    renderAdmin()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '新书审核' }))
    await screen.findByRole('heading', { name: '活着' })

    await user.type(screen.getByLabelText('驳回原因（会显示给作者）'), '与现有书目重复')
    await user.click(screen.getByRole('button', { name: '驳回' }))

    await waitFor(() =>
      expect(mockedApi.adminReview).toHaveBeenCalledWith(7, false, '与现有书目重复', ''),
    )
  })

  it('批准之后重新拉一遍队列', async () => {
    mockedApi.adminReviewQueue.mockResolvedValue([REVIEW_ROW])
    mockedApi.adminReview.mockResolvedValue({ ...REVIEW_ROW, visibility: 'public' })
    renderAdmin()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '新书审核' }))
    await screen.findByRole('heading', { name: '活着' })

    await user.click(screen.getByRole('button', { name: '批准公开' }))
    await waitFor(() => expect(mockedApi.adminReviewQueue.mock.calls.length).toBeGreaterThan(1))
  })
})

describe('用户管理', () => {
  async function openUsers() {
    renderAdmin()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '用户' }))
    await screen.findByText('bob@example.com')
    return user
  }

  it('列出用户，标出自己那一行', async () => {
    await openUsers()
    expect(screen.getByText('admin@test.local')).toBeInTheDocument()
    expect(screen.getByText('（你）')).toBeInTheDocument()
  })

  it('搜索停手之后才发请求——中间那些字不各发一次', async () => {
    // 30 个账号之后这一页需要"找"人了。逐字发请求在本地看不出问题，但它让
    // 每次输入都产生一串请求，且最后一个到得最晚——防抖后只发一次。
    const user = await openUsers()
    mockedApi.adminUsers.mockClear()

    await user.type(screen.getByLabelText('搜索邮箱、昵称或 id'), 'bob')

    await waitFor(() => expect(mockedApi.adminUsers).toHaveBeenCalledWith('bob'), {
      timeout: 2000,
    })
    // 没有防抖时这里是 ['b', 'bo', 'bob']
    expect(mockedApi.adminUsers.mock.calls.map(call => call[0])).toEqual(['bob'])
  })

  it('搜到几个就说几个，清空按钮把搜索撤掉', async () => {
    const user = await openUsers()
    mockedApi.adminUsers.mockResolvedValue([PLAIN])

    const box = screen.getByLabelText('搜索邮箱、昵称或 id')
    await user.type(box, 'bob')
    expect(await screen.findByText('找到 1 个用户')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '清空' }))
    expect(box).toHaveValue('')
    await waitFor(() => expect(mockedApi.adminUsers).toHaveBeenLastCalledWith(''), {
      timeout: 2000,
    })
  })

  it('搜不到时说"没有匹配的用户"，而不是"还没有用户"', async () => {
    // 这两句话指向完全不同的下一步：一个是"换个人名再搜"，一个是"去把人注册进来"。
    mockedApi.adminUsers.mockResolvedValue([])
    renderAdmin()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '用户' }))

    expect(await screen.findByText('还没有别的用户')).toBeInTheDocument()

    await user.type(screen.getByLabelText('搜索邮箱、昵称或 id'), 'zzz')

    expect(await screen.findByText('没有匹配的用户')).toBeInTheDocument()
    expect(screen.queryByText('还没有别的用户')).not.toBeInTheDocument()
  })

  it('搜索期间列表不整块换成骨架屏——输入框得留在原地', async () => {
    // 早先这一页是"loading 就整块换成 Loading"，加上搜索之后那意味着**每敲一个
    // 字，输入框被卸载一次、焦点丢一次**。现在只有"一行数据都还没有"才是骨架屏。
    const user = await openUsers()
    let release: ((rows: AdminUserRow[]) => void) | undefined
    mockedApi.adminUsers.mockImplementation(
      () => new Promise(resolve => { release = resolve }),
    )

    const box = screen.getByLabelText('搜索邮箱、昵称或 id')
    await user.type(box, 'bob')
    await waitFor(() => expect(release).toBeDefined(), { timeout: 2000 })

    expect(screen.getByLabelText('搜索邮箱、昵称或 id')).toBeInTheDocument()
    expect(screen.getByText('bob@example.com')).toBeInTheDocument()

    release?.([PLAIN])
    await waitFor(() => expect(screen.queryByText('admin@test.local')).not.toBeInTheDocument())
  })

  it('不能取消自己的管理员——按钮直接禁用', async () => {
    // 后端也会挡（400），但让用户点到一个注定失败的按钮、再看一条错误，
    // 不如一开始就不给这个选项。
    await openUsers()
    const buttons = screen.getAllByRole('button', { name: '取消管理员' })
    expect(buttons).toHaveLength(1)
    expect(buttons[0]).toBeDisabled()
  })

  it('不能删除自己，但可以删别人', async () => {
    await openUsers()
    const buttons = screen.getAllByRole('button', { name: '删除用户' })
    // 列表顺序是 [自己, bob]：自己那行的按钮被禁用，别人的照常可点
    expect(buttons[0]).toBeDisabled()
    expect(buttons[1]).toBeEnabled()
  })

  it('可以给别的用户授予管理员', async () => {
    mockedApi.adminSetAdmin.mockResolvedValue({ ...PLAIN, is_admin: true })
    const user = await openUsers()

    await user.click(screen.getByRole('button', { name: '设为管理员' }))
    await waitFor(() => expect(mockedApi.adminSetAdmin).toHaveBeenCalledWith(5, true))
  })

  it('重置密码要填够 8 位才能提交', async () => {
    const user = await openUsers()
    await user.click(screen.getAllByRole('button', { name: '重置密码' })[1])

    const input = await screen.findByLabelText('新密码（至少 8 位）')
    const save = screen.getByRole('button', { name: '保存' })
    expect(save).toBeDisabled()

    await user.type(input, 'short')
    expect(save).toBeDisabled()

    await user.type(input, 'enough123')
    expect(save).toBeEnabled()
  })

  it('点开详情，问答、书架、画像都聚在这一处', async () => {
    const user = await openUsers()
    // 列表顺序是 [自己, bob]，详情就跟在 bob 那一行下面
    await user.click(screen.getAllByRole('button', { name: '详情' })[1])

    expect(await screen.findByText('我最近很焦虑')).toBeInTheDocument()
    expect(screen.getByText('活着')).toBeInTheDocument()
    expect(screen.getByText('做事偏谨慎')).toBeInTheDocument()
    expect(mockedApi.adminUserDetail).toHaveBeenCalledWith(5)
  })

  it('一次只展开一个人的详情', async () => {
    const user = await openUsers()
    await user.click(screen.getAllByRole('button', { name: '详情' })[1])
    await waitFor(() => expect(mockedApi.adminUserDetail).toHaveBeenCalledWith(5))
    expect(screen.getAllByRole('button', { name: '收起' })).toHaveLength(1)

    await user.click(screen.getAllByRole('button', { name: '详情' })[0])
    await waitFor(() => expect(mockedApi.adminUserDetail).toHaveBeenCalledWith(1))
    // 上一个已经收起了：几个人的问答同时铺开，这一页就没法看了
    expect(screen.getAllByRole('button', { name: '收起' })).toHaveLength(1)
  })

  it('详情读不到时如实说，而不是显示成"这个人什么都没干过"', async () => {
    mockedApi.adminUserDetail.mockRejectedValue(new Error('数据库暂不可用，请稍后再试'))
    const user = await openUsers()
    await user.click(screen.getAllByRole('button', { name: '详情' })[1])

    expect(await screen.findByText('数据库暂不可用，请稍后再试')).toBeInTheDocument()
  })
})

describe('数据库浏览', () => {
  const COLUMNS = [
    { name: 'id', type: 'INTEGER', notnull: true, pk: true, protected: false },
    { name: 'email', type: 'TEXT', notnull: true, pk: false, protected: false },
    { name: 'password_hash', type: 'TEXT', notnull: true, pk: false, protected: true },
  ]

  async function openDb() {
    mockedApi.adminTable.mockResolvedValue({
      table: 'users',
      columns: COLUMNS,
      total: 2,
      rows: [
        { _rowid: 1, id: 1, email: 'admin@test.local', password_hash: 'abc123' },
        { _rowid: 2, id: 2, email: 'bob@example.com', password_hash: 'def456' },
      ],
    })
    renderAdmin()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '数据库' }))
    await screen.findByText('admin@test.local')
    return user
  }

  it('列出表与行数', async () => {
    await openDb()
    expect(screen.getByRole('button', { name: /users/ })).toBeInTheDocument()
  })

  it('受保护的列标出来，且编辑时不出现输入框', async () => {
    const user = await openDb()
    expect(screen.getAllByText('受保护').length).toBeGreaterThan(0)

    await user.click(screen.getAllByRole('button', { name: '编辑' })[0])

    // 邮箱可改
    expect(screen.getByDisplayValue('admin@test.local')).toBeInTheDocument()
    // 密码哈希不可改——绕过哈希逻辑写进去只会让这个人永远登不上
    expect(screen.queryByDisplayValue('abc123')).not.toBeInTheDocument()
    expect(screen.getByText('abc123')).toBeInTheDocument()
  })

  it('保存时按列类型还原成数字，而不是一律送字符串', async () => {
    // SQLite 里 `"1"` 与 `1` 在 INTEGER 列上虽然多数情况能转换，
    // 但把值当文本送回去迟早会在某个列上出岔子。
    const user = await openDb()
    await user.click(screen.getAllByRole('button', { name: '编辑' })[0])

    const emailInput = screen.getByDisplayValue('admin@test.local')
    await user.clear(emailInput)
    await user.type(emailInput, 'root@test.local')
    await user.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() =>
      expect(mockedApi.adminUpdateRow).toHaveBeenCalledWith('users', 1, {
        id: 1,
        email: 'root@test.local',
      }),
    )
  })

  it('删行要先确认', async () => {
    mockedApi.adminDeleteRow.mockResolvedValue({ ok: true })
    const user = await openDb()

    await user.click(screen.getAllByRole('button', { name: '删除' })[0])
    expect(mockedApi.adminDeleteRow).not.toHaveBeenCalled()

    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: '确认删除' }))
    await waitFor(() => expect(mockedApi.adminDeleteRow).toHaveBeenCalledWith('users', 1))
  })

  it('页脚写着总行数，翻页按钮按边界禁用', async () => {
    await openDb()
    expect(screen.getByText(/2 行/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled()
  })

  it('审计记录把机器动作名翻成人话', async () => {
    mockedApi.adminAudit.mockResolvedValue([
      {
        id: 1,
        user_id: 1,
        action: 'approve_book',
        target: 'user_book:7',
        detail: '与现有书目重复',
        created_at: '2026-09-24T14:00:00+00:00',
      },
    ])
    await openDb()
    expect(await screen.findByText('批准公开')).toBeInTheDocument()
    expect(screen.getByText('user_book:7')).toBeInTheDocument()
  })
})

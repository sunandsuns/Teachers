import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import { AuthProvider, useAuth } from '../features/auth/AuthProvider'
import LoginGate from '../features/auth/LoginGate'
import Login from '../pages/Login'
import Register from '../pages/Register'
import { I18nProvider } from '../i18n'

vi.mock('../api/client', () => ({
  api: {
    me: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    listShelf: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

const ALICE = {
  id: 2,
  email: 'alice@example.com',
  display_name: '小艾',
  name: '小艾',
  is_admin: false,
  created_at: '2026-09-24T10:00:00+00:00',
}

/** 把页面放进真实的那套 Provider 里。
 *
 * `initialEntries` 是为了测"从哪儿来、登完回哪儿去"——那个 `state.from`
 * 只有真的经过路由才存在。 */
function renderApp(ui: React.ReactNode, entries: string[] = ['/login']) {
  return render(
    <I18nProvider>
      <MemoryRouter initialEntries={entries}>
        <AuthProvider>{ui}</AuthProvider>
      </MemoryRouter>
    </I18nProvider>,
  )
}

/** 一个把 auth 值打出来的探针，用来断言 Provider 的状态。 */
function Probe() {
  const { user, loading } = useAuth()
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="user">{user ? user.name : 'null'}</span>
    </div>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.me.mockResolvedValue({ user: null })
})

describe('AuthProvider', () => {
  it('启动时问一次 /auth/me，未登录就是未登录（不是错误）', async () => {
    renderApp(<Probe />)
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('user')).toHaveTextContent('null')
    expect(mockedApi.me).toHaveBeenCalledTimes(1)
  })

  it('/auth/me 拿到用户就处于已登录态', async () => {
    mockedApi.me.mockResolvedValue({ user: ALICE })
    renderApp(<Probe />)
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('小艾'))
  })

  it('/auth/me 失败时按未登录处理，不把整页炸掉', async () => {
    // 后端没起来、断网——此时**匿名状态本来就能用**，
    // 弹一个红色报错只会让人以为产品坏了。
    mockedApi.me.mockRejectedValue(new Error('网络断了'))
    renderApp(<Probe />)
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('user')).toHaveTextContent('null')
  })
})

describe('登录页', () => {
  it('填邮箱密码提交，成功后离开登录页', async () => {
    const user = userEvent.setup()
    mockedApi.login.mockResolvedValue(ALICE)

    renderApp(
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/shelf" element={<div>我的书架内容</div>} />
      </Routes>,
    )

    await waitFor(() => expect(screen.getByLabelText('邮箱')).toBeInTheDocument())
    await user.type(screen.getByLabelText('邮箱'), 'alice@example.com')
    await user.type(screen.getByLabelText('密码'), 'goodpass123')
    await user.click(screen.getByRole('button', { name: '登录' }))

    await waitFor(() => expect(mockedApi.login).toHaveBeenCalledWith('alice@example.com', 'goodpass123'))
    expect(await screen.findByText('我的书架内容')).toBeInTheDocument()
  })

  it('登录失败时把后端给的原因原样显示出来', async () => {
    const user = userEvent.setup()
    mockedApi.login.mockRejectedValue(new Error('邮箱或密码不正确'))

    renderApp(<Login />)
    await waitFor(() => expect(screen.getByLabelText('邮箱')).toBeInTheDocument())
    await user.type(screen.getByLabelText('邮箱'), 'alice@example.com')
    await user.type(screen.getByLabelText('密码'), 'wrongpass')
    await user.click(screen.getByRole('button', { name: '登录' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('邮箱或密码不正确')
  })

  it('登录页明说"不登录也能用"', async () => {
    // 这不是客套话：检索、阅读、求教确实对匿名开放。把这句话藏起来，
    // 会让用户以为必须先注册才能进门。
    renderApp(<Login />)
    expect(await screen.findByText('不登录也能用')).toBeInTheDocument()
  })

  it('已经登录的人停在登录页上，看到的是"去书架"而不是表单', async () => {
    mockedApi.me.mockResolvedValue({ user: ALICE })
    renderApp(<Login />)
    expect(await screen.findByText('已登录 · 小艾')).toBeInTheDocument()
    expect(screen.queryByLabelText('邮箱')).not.toBeInTheDocument()
  })
})

describe('注册页', () => {
  it('比登录页多一个昵称字段，且昵称可留空', async () => {
    const user = userEvent.setup()
    mockedApi.register.mockResolvedValue(ALICE)

    renderApp(
      <Routes>
        <Route path="/register" element={<Register />} />
        <Route path="/shelf" element={<div>我的书架内容</div>} />
      </Routes>,
      ['/register'],
    )

    await waitFor(() => expect(screen.getByLabelText('邮箱')).toBeInTheDocument())
    expect(screen.getByLabelText('昵称（可留空）')).toBeInTheDocument()

    await user.type(screen.getByLabelText('邮箱'), 'alice@example.com')
    await user.type(screen.getByLabelText('密码'), 'goodpass123')
    await user.click(screen.getByRole('button', { name: '注册并登录' }))

    await waitFor(() =>
      expect(mockedApi.register).toHaveBeenCalledWith('alice@example.com', 'goodpass123', ''),
    )
    expect(await screen.findByText('我的书架内容')).toBeInTheDocument()
  })

  it('密码框用 new-password，让密码管理器知道这是注册', async () => {
    renderApp(<Register />, ['/register'])
    await waitFor(() => expect(screen.getByLabelText('密码')).toBeInTheDocument())
    expect(screen.getByLabelText('密码')).toHaveAttribute('autocomplete', 'new-password')
  })
})

describe('LoginGate', () => {
  it('加载中先不结论——不闪一下"请先登录"', async () => {
    let release: (value: { user: null }) => void = () => {}
    mockedApi.me.mockReturnValue(new Promise(resolve => {
      release = resolve
    }))

    renderApp(
      <LoginGate>
        <div>私密内容</div>
      </LoginGate>,
    )

    expect(screen.getByText('加载中…')).toBeInTheDocument()
    expect(screen.queryByText('需要先登录')).not.toBeInTheDocument()

    release({ user: null })
    expect(await screen.findByText('需要先登录')).toBeInTheDocument()
  })

  it('未登录时给出出口，且把来路带上', async () => {
    const user = userEvent.setup()
    /** 把登录页收到的 `state.from` 打出来。用户从「我的书架」被拦下来，
     *  登完就该回到「我的书架」——不带这个信息就会丢到首页，还得自己再点一次。 */
    function LoginStub() {
      const location = useLocation()
      const from = (location.state as { from?: string } | null)?.from ?? '（没有）'
      return <div>登录页 from={from}</div>
    }

    renderApp(
      <Routes>
        <Route
          path="/shelf"
          element={
            <LoginGate>
              <div>私密内容</div>
            </LoginGate>
          }
        />
        <Route path="/login" element={<LoginStub />} />
      </Routes>,
      ['/shelf'],
    )

    await user.click(await screen.findByRole('button', { name: '去登录' }))
    expect(await screen.findByText('登录页 from=/shelf')).toBeInTheDocument()
  })

  it('已登录时直接渲染内容', async () => {
    mockedApi.me.mockResolvedValue({ user: ALICE })
    renderApp(
      <LoginGate>
        <div>私密内容</div>
      </LoginGate>,
    )
    expect(await screen.findByText('私密内容')).toBeInTheDocument()
  })
})

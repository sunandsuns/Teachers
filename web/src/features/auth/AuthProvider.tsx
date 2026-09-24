import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api, type UserInfo } from '../../api/client'

/**
 * 登录状态。
 *
 * 为什么放在 context 而不是每个页面各自 `api.me()`
 * --------------------------------------------------------------------------
 * 顶栏要显示"登录 / 用户名"，书架页要知道该不该提示登录，后台页要判断
 * 是不是管理员——三处都要同一份答案。各自去问一次，就会出现"顶栏已经显示
 * 登录了、书架页还在说未登录"的中间态，而且切一次页就多一次往返。
 *
 * 未登录是一个**正常状态**，不是错误：`user` 为 null 而已。整套检索、阅读、
 * 求教都对匿名开放，所以这里没有 `error` 字段——只有 `/auth/me` 真的失败
 * （网络断了、后端没起来）时才需要说话，那种情况下按未登录处理更安全。
 */
export interface AuthValue {
  /** 当前用户；未登录为 null */
  user: UserInfo | null
  /** 启动时那次 `/auth/me` 还没回来。**为 true 时不要下"未登录"的结论** */
  loading: boolean
  login: (email: string, password: string) => Promise<UserInfo>
  register: (email: string, password: string, displayName?: string) => Promise<UserInfo>
  logout: () => Promise<void>
  /**
   * 本地立刻回到未登录，不发请求。
   *
   * 改密码之后用：后端已经把这个人的**全部会话**作废了，本地还留着一个
   * 已经失效的用户对象，页面会继续按"已登录"渲染，然后所有请求 401。
   */
  forget: () => void
}

/**
 * 没有 Provider 时的取值。
 *
 * 单测经常直接渲染某一页（不套 Provider）。这里给一个"未登录、且不在加载中"
 * 的稳定值，页面会走到"请先登录"那条分支，而不是炸掉。
 */
const FALLBACK: AuthValue = {
  user: null,
  loading: false,
  login: () => Promise.reject(new Error('AuthProvider is not mounted')),
  register: () => Promise.reject(new Error('AuthProvider is not mounted')),
  logout: () => Promise.resolve(),
  forget: () => {},
}

const Ctx = createContext<AuthValue>(FALLBACK)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    api
      .me()
      .then(res => {
        if (!cancelled) setUser(res.user)
      })
      .catch(() => {
        // 问不到就按未登录算。弹一个红色报错没有意义——匿名状态本来就能用，
        // 而真的连不上后端时，后面每个请求都会各自报错，不缺这一条。
        if (!cancelled) setUser(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const next = await api.login(email, password)
    setUser(next)
    return next
  }, [])

  const register = useCallback(
    async (email: string, password: string, displayName = '') => {
      const next = await api.register(email, password, displayName)
      setUser(next)
      return next
    },
    [],
  )

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      // 就算请求失败，本地也必须退出：用户点的是"退出登录"，
      // 让界面继续显示已登录，比"服务端那条会话没删掉"更糟。
      setUser(null)
    }
  }, [])

  const forget = useCallback(() => setUser(null), [])

  const value = useMemo<AuthValue>(
    () => ({ user, loading, login, register, logout, forget }),
    [user, loading, login, register, logout, forget],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthValue {
  return useContext(Ctx)
}

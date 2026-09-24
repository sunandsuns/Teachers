import type { ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Button, Empty } from '../../components/ui'
import { Loading } from '../../components/Status'
import { useI18n } from '../../i18n'
import { useAuth } from './AuthProvider'

/**
 * 「这一页要登录才能看」。
 *
 * 三件事，顺序不能换：
 *
 * 1. **加载中不能当作未登录。** 启动时那次 `/auth/me` 还没回来，此刻下
 *    "未登录"的结论会让已登录的用户看到一闪而过的登录门。所以先显示 Loading。
 * 2. **要把来路带上。** 用户从「寻章」被拦下来，登完就该回到「寻章」。
 *    `state.from` 就是这个用途，在页面里写比在路由层拼更清楚。
 * 3. **不跳走。** 门是"停在原地把话说明白"，不是把用户从一个页面扔到另一个
 *    页面。URL 不变、后退键不乱，用户知道自己在哪儿、为什么进不去。
 *
 * 应用在哪儿
 * --------------------------------------------------------------------------
 * 实际拦住整组路由的是 `RequireAuth`（一条无路径的布局路由），它把
 * `<Outlet />` 塞进这个组件。这样"哪些页面要登录"只在路由表里说一次。
 * 这个文件只管**门长什么样**，不管**哪些路由有门**——两件事分开，
 * 单测里可以直接渲染它，不必先搭一套路由。
 */
export default function LoginGate({
  children,
  hint,
}: {
  children?: ReactNode
  /** 换一句更贴切的说明（如「寻章」要登录之后才能用）。不给就用通用那句。 */
  hint?: ReactNode
}) {
  const { t } = useI18n()
  const { user, loading } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  if (loading) return <Loading />
  if (user) return <>{children}</>

  return (
    <Empty
      title={t('auth.needLogin')}
      hint={hint ?? t('auth.needLoginHint')}
      action={
        <Button
          onClick={() =>
            navigate('/login', { state: { from: `${location.pathname}${location.search}` } })
          }
        >
          {t('auth.goLogin')}
        </Button>
      }
    />
  )
}

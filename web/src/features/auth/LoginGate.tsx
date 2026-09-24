import type { ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Button, Empty } from '../../components/ui'
import { Loading } from '../../components/Status'
import { useI18n } from '../../i18n'
import { useAuth } from './AuthProvider'

/**
 * 「这一页属于你自己，得先登录」。
 *
 * 做成组件而不是路由守卫（`<Navigate to="/login">`），有两个理由：
 *
 * 1. **加载中不能当作未登录。** 启动时那次 `/auth/me` 还没回来，此刻跳转到
 *    登录页会让已登录的用户看到一闪而过的登录界面。所以先显示 Loading。
 * 2. **要把来路带上。** 用户从「我的书架」被拦下来，登完就该回到「我的书架」。
 *    `state.from` 就是这个用途，在页面里写比在路由层拼更清楚。
 *
 * 用 `Empty` 而不是整页跳转，是因为"未登录"在这套产品里不是错误：说清楚
 * 这一页要什么、并给一个出口，比把用户从一个页面扔到另一个页面友好。
 */
export default function LoginGate({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  const { user, loading } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  if (loading) return <Loading />
  if (user) return <>{children}</>

  return (
    <Empty
      title={t('auth.needLogin')}
      hint={t('auth.needLoginHint')}
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

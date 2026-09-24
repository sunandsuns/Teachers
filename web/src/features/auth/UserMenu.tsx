import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useI18n } from '../../i18n'
import { useAuth } from './AuthProvider'

/**
 * 顶栏右侧的账号入口。
 *
 * 两种形态，因为这两种状态要做的事根本不是一回事：
 *
 * - **未登录**：直接给一个「登录」链接。这时候给个下拉菜单，用户还要多点一次
 *   才知道里面有什么；而他要做的事只有一件。
 * - **已登录**：一个下拉菜单（昵称 + 我的书架 / 后台 / 退出登录）。这三件事
 *   都不常做，常驻在顶栏会把导航挤得更窄。
 *
 * 菜单本身是**受控的普通 div**，不是 `<details>` 也不是第三方组件：要处理
 * 的只有三件事——点外面关掉、按 Esc 关掉、点里面任何一项关掉。为了这三件事
 * 引入一个依赖不划算。
 */
export default function UserMenu() {
  const { t } = useI18n()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  // 点面板外面 / 按 Esc 就收起。挂在 document 上而不是靠 onBlur：
  // 鼠标按下与焦点移出是两回事，用 blur 会在点面板内部时就把菜单关掉。
  useEffect(() => {
    if (!open) return
    function onPointerDown(event: MouseEvent) {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  if (!user) {
    return (
      <Link
        to="/login"
        className="shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium text-ink-600 transition-colors duration-quick hover:bg-paper-200 hover:text-ink-900"
      >
        {t('auth.login')}
      </Link>
    )
  }

  const initial = (user.name || user.email).slice(0, 1).toUpperCase()

  return (
    <div ref={boxRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen(value => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={t('auth.menu')}
        className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-2 transition-colors duration-quick hover:bg-paper-200"
      >
        <span
          aria-hidden="true"
          className="flex h-6 w-6 items-center justify-center rounded-full bg-cinnabar-500 text-xs font-semibold text-paper-50"
        >
          {initial}
        </span>
        <span className="hidden max-w-[7rem] truncate text-sm font-medium text-ink-700 sm:block">
          {user.name}
        </span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-30 mt-1.5 w-52 origin-top-right overflow-hidden rounded-xl border border-paper-300 bg-paper-50 py-1 shadow-lift animate-fade-in"
        >
          <div className="truncate px-3 py-2 text-xs text-ink-400">{user.email}</div>
          <MenuLink to="/shelf" onNavigate={() => setOpen(false)}>
            {t('nav.mine')}
          </MenuLink>
          {user.is_admin && (
            <MenuLink to="/admin" onNavigate={() => setOpen(false)}>
              {t('nav.admin')}
            </MenuLink>
          )}
          <button
            type="button"
            role="menuitem"
            onClick={async () => {
              setOpen(false)
              await logout()
              // 退出之后停在原地会把"我的书架"渲染成"请先登录"，
              // 不如回首页——那是所有人都能看的一页。
              navigate('/')
            }}
            className="w-full px-3 py-2 text-left text-sm text-ink-600 transition-colors duration-quick hover:bg-paper-200 hover:text-cinnabar-600"
          >
            {t('auth.logout')}
          </button>
        </div>
      )}
    </div>
  )
}

function MenuLink({
  to,
  onNavigate,
  children,
}: {
  to: string
  onNavigate: () => void
  children: React.ReactNode
}) {
  return (
    <Link
      to={to}
      role="menuitem"
      onClick={onNavigate}
      className="block px-3 py-2 text-sm text-ink-600 transition-colors duration-quick hover:bg-paper-200 hover:text-ink-900"
    >
      {children}
    </Link>
  )
}

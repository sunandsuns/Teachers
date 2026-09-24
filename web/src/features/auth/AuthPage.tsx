import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Button, Card } from '../../components/ui'
import { useI18n } from '../../i18n'
import { useAuth } from './AuthProvider'

/** 两个模式共用一张表：字段只差一个昵称，逻辑只差一个 API 调用。 */
export type AuthMode = 'login' | 'register'

interface FieldProps {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
  placeholder?: string
  hint?: string
  autoComplete?: string
  autoFocus?: boolean
  required?: boolean
}

/** 一个带标签的输入框。
 *
 * 标签用 `<label htmlFor>` 真正绑上去，而不是把文字摆在输入框旁边——
 * 后者点标签不会聚焦、读屏也念不出这个框是干什么的。
 */
function Field({
  id,
  label,
  value,
  onChange,
  type = 'text',
  placeholder,
  hint,
  autoComplete,
  autoFocus,
  required,
}: FieldProps) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink-700">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        autoFocus={autoFocus}
        required={required}
        className="w-full rounded-lg border border-paper-300 bg-paper-50 px-3 py-2 text-sm text-ink-900 outline-none transition-[border-color,box-shadow] duration-quick placeholder:text-ink-300 focus:border-cinnabar-400 focus:ring-2 focus:ring-cinnabar-500/15"
      />
      {hint && <p className="mt-1.5 text-xs text-ink-400">{hint}</p>}
    </div>
  )
}

/**
 * 登录 / 注册页。
 *
 * 两页共用一个组件：它们的版式完全一样，字段只差一个"昵称"，动作只差一个
 * API 调用。拆成两份文件的结果一定是"改了一边忘了另一边"——比如某天要给
 * 密码框加上显示/隐藏，就得记得改两处。
 *
 * 一个刻意的取舍：**登录页不把"不登录也能用"藏起来**。这套产品的检索、阅读、
 * 求教本来就对所有人开放，登录只决定"哪些数据归你"；把这句话说出来，比让
 * 用户以为必须先注册才能进门要诚实得多。
 */
export default function AuthPage({ mode }: { mode: AuthMode }) {
  const { t } = useI18n()
  const { login, register, user, loading: authLoading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const isLogin = mode === 'login'

  /** 登录成功之后去哪。
   *
   * 从「我的书架」被弹过来的用户，`location.state.from` 记着原地址——登完直接
   * 送回去，而不是丢到首页让他再点一次。
   */
  const from = (location.state as { from?: string } | null)?.from ?? '/shelf'

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setError('')
    setBusy(true)
    try {
      if (isLogin) await login(email.trim(), password)
      else await register(email.trim(), password, displayName.trim())
      navigate(from, { replace: true })
    } catch (err) {
      // 后端已经把"邮箱已被注册""邮箱或密码不正确"这类话写成了人话，
      // 直接显示它；这里不再自己编一套，免得两边说不到一块去。
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  // 已经登录的人不该停在登录页上——多半是点了后退，或者手动输了地址。
  if (!authLoading && user) {
    return (
      <AuthShell title={t('auth.loginTitle')}>
        <p className="text-sm text-ink-600">{t('auth.signedInAs', { name: user.name })}</p>
        <div className="mt-4 flex gap-2">
          <Button onClick={() => navigate('/shelf')}>{t('nav.mine')}</Button>
          <Button variant="secondary" onClick={() => navigate('/')}>
            {t('nav.library')}
          </Button>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell title={isLogin ? t('auth.loginTitle') : t('auth.registerTitle')}>
      <p className="mb-6 text-sm text-ink-500">
        {isLogin ? t('auth.loginDesc') : t('auth.registerDesc')}
      </p>

      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Field
          id="auth-email"
          label={t('auth.email')}
          value={email}
          onChange={setEmail}
          type="email"
          placeholder={t('auth.emailPlaceholder')}
          autoComplete="email"
          autoFocus
          required
        />
        <Field
          id="auth-password"
          label={t('auth.password')}
          value={password}
          onChange={setPassword}
          type="password"
          placeholder={t('auth.passwordPlaceholder')}
          // 浏览器密码管理器靠这个属性区分"登录"与"注册"，
          // 写错会让它填错字段、或者干脆不弹保存密码的提示
          autoComplete={isLogin ? 'current-password' : 'new-password'}
          hint={isLogin ? undefined : t('auth.passwordPlaceholder')}
          required
        />
        {!isLogin && (
          <Field
            id="auth-name"
            label={t('auth.displayName')}
            value={displayName}
            onChange={setDisplayName}
            placeholder={t('auth.displayNamePlaceholder')}
            autoComplete="nickname"
          />
        )}

        {error && (
          <p
            role="alert"
            className="rounded-lg border border-cinnabar-200 bg-cinnabar-50 px-3 py-2 text-sm text-cinnabar-700 animate-fade-in"
          >
            {error}
          </p>
        )}

        <Button type="submit" loading={busy} className="w-full">
          {isLogin ? t('auth.loginAction') : t('auth.registerAction')}
        </Button>
      </form>

      <Link
        to={isLogin ? '/register' : '/login'}
        className="mt-4 block text-center text-sm text-ink-500 transition-colors duration-quick hover:text-cinnabar-600"
      >
        {isLogin ? t('auth.toRegister') : t('auth.toLogin')}
      </Link>

      <p className="mt-6 border-t border-paper-200 pt-4 text-xs leading-relaxed text-ink-400">
        <span className="font-medium text-ink-500">{t('auth.optional')}</span>
        {' · '}
        {t('auth.optionalHint')}
      </p>
    </AuthShell>
  )
}

/** 版式外壳。窄一点（`max-w-sm`）：表单一行只有两个字段，铺满 5xl 会显得空。 */
function AuthShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mx-auto max-w-sm pt-6">
      <Card className="p-6 sm:p-7">
        <h1 className="mb-2 font-serif text-2xl font-bold tracking-tight text-ink-900">
          {title}
        </h1>
        {children}
      </Card>
    </section>
  )
}

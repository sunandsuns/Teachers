import { useState } from 'react'
import { api, type AdminUserRow } from '../../api/client'
import { Badge, Button, Card, ConfirmBar } from '../../components/ui'
import { ErrorBox, Loading } from '../../components/Status'
import { useAuth } from '../auth/AuthProvider'
import { useI18n } from '../../i18n'
import { shortTime } from './constants'

interface UsersPanelProps {
  rows: AdminUserRow[] | null
  loading: boolean
  error: string | null
  /** 改完之后让上层重新拉一遍（总览里的用户数也跟着变） */
  onChanged: () => void
}

/**
 * 用户管理。
 *
 * 两条**自保规则**，前后端各写一遍：
 *
 * - **不能取消自己的管理员**。这个系统没有命令行工具能把人放回管理员，
 *   点错一次就等于把自己锁在门外。
 * - **不能删除自己**。同上，而且更彻底。
 *
 * 后端已经挡住了（返回 400），这里仍然把按钮藏起来：让用户点到一个注定失败
 * 的按钮、再看一条错误，不如一开始就不给这个选项。**两处都要有**——前端管
 * 体验，后端管安全，谁也不能替谁。
 */
export default function UsersPanel({ rows, loading, error, onChanged }: UsersPanelProps) {
  const { t } = useI18n()
  const { user: me } = useAuth()
  const [busy, setBusy] = useState<number | null>(null)
  const [failure, setFailure] = useState('')
  const [resetting, setResetting] = useState<AdminUserRow | null>(null)
  const [deleting, setDeleting] = useState<AdminUserRow | null>(null)

  if (error) return <ErrorBox message={error} />
  if (loading) return <Loading />

  const users = rows ?? []

  async function toggleAdmin(row: AdminUserRow) {
    setBusy(row.id)
    setFailure('')
    try {
      await api.adminSetAdmin(row.id, !row.is_admin)
      onChanged()
    } catch (err) {
      setFailure(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      {failure && <ErrorBox message={failure} />}

      {resetting && (
        <ResetForm
          row={resetting}
          onCancel={() => setResetting(null)}
          onDone={() => {
            setResetting(null)
            onChanged()
          }}
        />
      )}

      {deleting && (
        <ConfirmBar
          message={`${t('admin.deleteUser')} ${deleting.email}？`}
          confirmLabel={t('common.confirmDelete')}
          busyLabel={t('common.deleting')}
          cancelLabel={t('common.cancel')}
          busy={busy === deleting.id}
          onCancel={() => setDeleting(null)}
          onConfirm={async () => {
            setBusy(deleting.id)
            setFailure('')
            try {
              await api.adminDeleteUser(deleting.id)
              setDeleting(null)
              onChanged()
            } catch (err) {
              setFailure(err instanceof Error ? err.message : String(err))
            } finally {
              setBusy(null)
            }
          }}
        />
      )}

      <div className="space-y-2">
        {users.map(row => {
          const isMe = me?.id === row.id
          return (
            <Card key={row.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 p-3">
              <span className="font-mono text-xs text-ink-300 tabular-nums">#{row.id}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-ink-800">
                  {row.email}
                  {isMe && <span className="ml-1.5 text-xs text-ink-400">（{t('admin.you')}）</span>}
                </span>
                <span className="block text-xs text-ink-400">
                  {[row.name, t('admin.shelfCount', { count: row.shelf_books }), shortTime(row.created_at)]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </span>

              {row.is_admin && <Badge tone="brand">{t('admin.stat.admins')}</Badge>}

              <span className="flex shrink-0 items-center gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={isMe || busy === row.id}
                  title={isMe ? t('admin.you') : undefined}
                  onClick={() => void toggleAdmin(row)}
                >
                  {row.is_admin ? t('admin.revokeAdmin') : t('admin.grantAdmin')}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setResetting(row)}>
                  {t('admin.resetPassword')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-ink-400 hover:text-cinnabar-600"
                  disabled={isMe}
                  title={isMe ? t('admin.you') : undefined}
                  onClick={() => setDeleting(row)}
                >
                  {t('admin.deleteUser')}
                </Button>
              </span>
            </Card>
          )
        })}
      </div>
    </div>
  )
}

/** 重置密码。**就地展开**，不弹窗——弹窗在嵌入式预览里会被静默拦掉。 */
function ResetForm({
  row,
  onCancel,
  onDone,
}: {
  row: AdminUserRow
  onCancel: () => void
  onDone: () => void
}) {
  const { t } = useI18n()
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  return (
    <Card className="p-4 animate-fade-up">
      <p className="mb-2 text-sm text-ink-700">
        {t('admin.resetPassword')} · {row.email}
      </p>
      <div className="flex flex-wrap gap-2">
        <input
          type="text"
          value={password}
          onChange={event => setPassword(event.target.value)}
          placeholder={t('admin.newPassword')}
          aria-label={t('admin.newPassword')}
          className="min-w-0 flex-1 basis-48 rounded-lg border border-paper-300 bg-paper-50 px-3 py-2 text-sm text-ink-900 outline-none transition-[border-color,box-shadow] duration-quick placeholder:text-ink-300 focus:border-cinnabar-400 focus:ring-2 focus:ring-cinnabar-500/15"
        />
        <Button
          size="sm"
          loading={busy}
          disabled={password.length < 8}
          onClick={async () => {
            setBusy(true)
            setError('')
            try {
              await api.adminResetPassword(row.id, password)
              onDone()
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err))
            } finally {
              setBusy(false)
            }
          }}
        >
          {t('common.save')}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
          {t('common.cancel')}
        </Button>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-xs text-cinnabar-600">
          {error}
        </p>
      )}
      <p className="mt-2 text-xs text-ink-400">{t('admin.resetDone')}</p>
    </Card>
  )
}

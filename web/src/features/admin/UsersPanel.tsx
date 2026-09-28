import { useState } from 'react'
import { api, type AdminUserRow } from '../../api/client'
import { Badge, Button, Card, Collapse, ConfirmBar, Empty } from '../../components/ui'
import { ErrorBox, Loading } from '../../components/Status'
import { useAuth } from '../auth/AuthProvider'
import { useI18n } from '../../i18n'
import UserDetailPanel from './UserDetailPanel'
import { shortTime } from './constants'

interface UsersPanelProps {
  rows: AdminUserRow[] | null
  loading: boolean
  error: string | null
  /** 改完之后让上层重新拉一遍（总览里的用户数也跟着变） */
  onChanged: () => void
  /** 搜索框里此刻打出来的内容（即时回显用） */
  search: string
  onSearch: (value: string) => void
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
 *
 * ## 搜索框，与"重新请求时列表不闪"
 *
 * 搜索走**后端**（`?q=`）：请求由 `AdminPage` 的 `useAsync` 发出，所以搜索期间
 * `loading` 会变 true。这里**不能**照着 `loading` 整块换成骨架屏——那会把输入框
 * 连同列表一起卸载掉，于是"每敲一个字，焦点就丢一次"。规则是：只有
 * `rows === null`（**还没有任何数据**）时 `loading` 才等于"这页还没准备好"；
 * 其余时候它只是"上面那份结果在更新"，旧列表继续显示、外层标成 `aria-busy`。
 *
 * 搜索框本身**永远在**，空态与错误态下也在：搜错了想改一个字母，不该先无路可走。
 */
export default function UsersPanel({
  rows,
  loading,
  error,
  onChanged,
  search,
  onSearch,
}: UsersPanelProps) {
  const { t } = useI18n()
  const { user: me } = useAuth()
  const [busy, setBusy] = useState<number | null>(null)
  const [failure, setFailure] = useState('')
  const [resetting, setResetting] = useState<AdminUserRow | null>(null)
  const [deleting, setDeleting] = useState<AdminUserRow | null>(null)
  /** 正在展开详情的那个人。**一次只开一个**——同时铺开几个人的问答，
   *  这页就没法看了，而且他多半也只需要比着看某一个。 */
  const [detailOf, setDetailOf] = useState<number | null>(null)

  const users = rows ?? []
  const searching = search.trim().length > 0

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
      <div className="flex items-center gap-2">
        <input
          type="search"
          value={search}
          onChange={event => onSearch(event.target.value)}
          placeholder={t('admin.searchUsers')}
          aria-label={t('admin.searchUsers')}
          className="min-w-0 flex-1 rounded-lg border border-paper-300 bg-paper-50 px-3 py-2 text-sm text-ink-900 outline-none transition-[border-color,box-shadow] duration-quick placeholder:text-ink-300 focus:border-cinnabar-400 focus:ring-2 focus:ring-cinnabar-500/15"
        />
        {searching && (
          <Button size="sm" variant="ghost" onClick={() => onSearch('')}>
            {t('admin.searchClear')}
          </Button>
        )}
      </div>

      {/* 搜到几个，说清楚。空态只写"没有匹配"会让人怀疑到底是在搜谁。 */}
      {searching && !error && users.length > 0 && (
        <p role="status" className="text-xs text-ink-400">
          {t('admin.searchFound', { count: users.length })}
        </p>
      )}

      {failure && <ErrorBox message={failure} />}
      {error && <ErrorBox message={error} />}

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

      {!error && rows === null && <Loading />}

      {!error && rows !== null && users.length === 0 && (
        <Empty
          title={searching ? t('admin.searchEmpty') : t('admin.empty')}
          hint={searching ? t('admin.searchEmptyHint') : t('admin.emptyHint')}
        />
      )}

      {/* 出错时**不留旧结果**：那份结果已经不能代表"此刻这一步查询"了，摆在
          错误下面会读成"搜到的就是这些"。 */}
      {!error && (
        <div className="space-y-2" aria-busy={loading}>
          {users.map(row => {
            const isMe = me?.id === row.id
            const opened = detailOf === row.id
            return (
              // 外层这一层只为"卡片 + 它自己的详情"成一组：详情要贴着这一行展开，
              // 而不是飘到列表末尾去。
              <div key={row.id} className="space-y-2">
                <Card className="flex flex-wrap items-center gap-x-3 gap-y-2 p-3">
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
                    {/* 读操作排在写操作前面：点进来看一眼是最常做的事，
                        而"取消管理员""删除"点错了不好收场。 */}
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-expanded={opened}
                      onClick={() => setDetailOf(opened ? null : row.id)}
                    >
                      {t('admin.detail')}
                    </Button>
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

                {opened && (
                  <Collapse>
                    <UserDetailPanel userId={row.id} onClose={() => setDetailOf(null)} />
                  </Collapse>
                )}
              </div>
            )
          })}
        </div>
      )}
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

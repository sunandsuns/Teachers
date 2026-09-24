import { useState } from 'react'
import { api } from '../../api/client'
import { Badge, Empty, PageHeader, Segmented } from '../../components/ui'
import { ErrorBox, Loading } from '../../components/Status'
import { useAsync } from '../../hooks/useAsync'
import { useI18n } from '../../i18n'
import { useAuth } from '../auth/AuthProvider'
import DatabasePanel from './DatabasePanel'
import OverviewPanel from './OverviewPanel'
import ReviewPanel from './ReviewPanel'
import UsersPanel from './UsersPanel'
import { ADMIN_TABS, TAB_KEY, type AdminTab } from './constants'

/**
 * 后台管理。
 *
 * 四块内容用一个页签切换，而不是四条独立路由：它们共用同一份"当前是管理员"
 * 的判断和同一批数据（总览里的用户数、待审数在别的面板里改完就要跟着变），
 * 拆成四条路由反而要把这些状态提到更外面。
 *
 * 权限判断分两层：**要不要登录**由路由表决定（`/admin` 在 `RequireAuth` 那一组里，
 * 未登录时根本走不到这里）；**是不是管理员**留在本页——"未登录"和"已登录但
 * 不是管理员"该看到的话不一样，前者是"你去登录"，后者是"你没这个权限"，
 * 那句区别只有这里说得清。真正的拦截在后端（`require_admin` → 403），
 * 界面这层只管说明。
 */
export default function AdminPage() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [tab, setTab] = useState<AdminTab>('overview')

  // 三个面板的数据都在这里拿：切页签不该重新请求一遍。
  // 非管理员时这些请求会各自收到 403——所以下面先判断身份，别白跑三趟。
  const isAdmin = Boolean(user?.is_admin)
  const overview = useAsync(
    () => (isAdmin ? api.adminOverview() : Promise.resolve(null)),
    [isAdmin],
  )
  const users = useAsync(() => (isAdmin ? api.adminUsers() : Promise.resolve(null)), [isAdmin])
  const review = useAsync(
    () => (isAdmin ? api.adminReviewQueue() : Promise.resolve(null)),
    [isAdmin],
  )

  // 外层 `RequireAuth` 保证到了这里一定有 user，这行只为把类型收窄成非空。
  // 不写 `return <Loading />`：万一真有路径漏过门禁，转圈比说清"要登录"更糟。
  if (!user) return null
  if (!user.is_admin) return <Empty title={t('admin.denied')} hint={t('admin.deniedHint')} />

  /** 任何一个面板改动了数据，总览里的计数就可能过时。一并刷新，代价是三次本地查询。 */
  function refreshAll() {
    overview.reload()
    users.reload()
    review.reload()
  }

  const pending = overview.data?.pending_review ?? 0

  return (
    <section>
      <PageHeader
        title={t('admin.title')}
        description={t('admin.description')}
      >
        {/* 待审数量挂在标题右边：这是管理员最需要被提醒的一个数，
            藏在「新书审核」页签里就得点进去才知道。为 0 时不显示——
            一个常年挂着的「0」会让人对这块标记失去感觉。 */}
        {pending > 0 && (
          <Badge tone="brand">
            {t('admin.stat.pending')} {pending}
          </Badge>
        )}
      </PageHeader>

      <div className="mb-6">
        <Segmented
          value={tab}
          ariaLabel={t('admin.title')}
          onChange={setTab}
          options={ADMIN_TABS.map(value => ({ value, label: t(TAB_KEY[value]) }))}
        />
      </div>

      {tab === 'overview' &&
        (overview.error ? (
          <ErrorBox message={overview.error} />
        ) : overview.loading || !overview.data ? (
          <Loading />
        ) : (
          <OverviewPanel data={overview.data} />
        ))}

      {tab === 'review' && (
        <ReviewPanel
          rows={review.data}
          loading={review.loading}
          error={review.error}
          onChanged={refreshAll}
        />
      )}

      {tab === 'users' && (
        <UsersPanel
          rows={users.data}
          loading={users.loading}
          error={users.error}
          onChanged={refreshAll}
        />
      )}

      {tab === 'db' && <DatabasePanel />}
    </section>
  )
}

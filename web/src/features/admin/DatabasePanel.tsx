import { useMemo, useState } from 'react'
import { api, type AuditEntry, type DbTableData } from '../../api/client'
import { Badge, Button, Card, Chip, ConfirmBar, Empty } from '../../components/ui'
import { ErrorBox, Loading } from '../../components/Status'
import { useAsync } from '../../hooks/useAsync'
import { useI18n } from '../../i18n'
import { delayStyle } from '../../lib/motion'
import { ACTION_LABEL, DB_PAGE_SIZE, cellText, shortTime } from './constants'

/**
 * 直接操作数据库。
 *
 * 这是整个系统里最容易把库搞坏的地方，所以界面上的三件事都必须**看得见**：
 *
 * 1. **哪些列不能改**。后端把 `users.password_hash` 与 `users.salt` 标成
 *    `protected`，这里把它们渲染成只读并挂上标记。绕过哈希逻辑写进去的值只会
 *    让这个人永远登不上，而且从界面上看不出哪里坏了。
 * 2. **改的是哪一行**。定位用 `_rowid` 而不是主键——`meta` 表的主键是 TEXT，
 *    `public_books` 的 `book_id` 与自增 id 也不是一回事。
 * 3. **改了什么**。每次写入都由后端记进审计，页面底部就摆着那份记录。
 *
 * 值一律当**文本**编辑，保存时再按列的类型还原成数字——不然 SQLite 会把
 * `0` 存成字符串 `"0"`，而 `WHERE is_admin = 1` 就再也匹配不上。
 */
export default function DatabasePanel() {
  const { t } = useI18n()
  const tables = useAsync(() => api.adminTables(), [])
  const [table, setTable] = useState('')
  const [offset, setOffset] = useState(0)

  const selected = table || tables.data?.[0]?.name || ''
  const data = useAsync(
    () => (selected ? api.adminTable(selected, DB_PAGE_SIZE, offset) : Promise.resolve(null)),
    [selected, offset],
  )

  if (tables.error) return <ErrorBox message={tables.error} />
  if (tables.loading) return <Loading />

  return (
    <div className="space-y-5">
      {/* 四个分页里「数据库」这一页最大也最杂（选表 → 数据表 → 说明 → 审计记录）。
          整页一起冒出来会像"刷"地换了张图，所以按**大块**错峰入场。

          粒度只做到大块，**不给表格行做**：`<tr>` 上加 transform 会牵动
          `sticky` 表头（位移的祖先会改变它的包含块），而且几十行一起位移
          比静止更晃眼。做到"眼睛读得出来的那一层"就够。

          这里用 `fade-up`（位移 6px / 220ms）而不是卡片用的 `rise`
          （位移 16px + 缩放 0.985 / 520ms）：`rise` 那个微缩放在一张大表上
          会看成版面在抖。 */}
      <div className="animate-fade-up" style={delayStyle(0, 60, 240)}>
        <h2 className="mb-2 font-serif text-base font-semibold text-ink-800">
          {t('admin.dbTitle')}
        </h2>
        <div className="flex flex-wrap gap-1.5">
          {(tables.data ?? []).map(item => (
            <Chip
              key={item.name}
              active={selected === item.name}
              count={item.rows}
              onClick={() => {
                setTable(item.name)
                // 换表必须回到第一页：上一张表的 offset 在这张表里多半越界，
                // 表现就是"点过去一片空白"。
                setOffset(0)
              }}
            >
              <span className="font-mono">{item.name}</span>
            </Chip>
          ))}
        </div>
      </div>

      <div className="animate-fade-up" style={delayStyle(1, 60, 240)}>
        {data.error && <ErrorBox message={data.error} />}
        {data.loading && <Loading />}
        {data.data && (
          <TableData
            key={data.data.table}
            data={data.data}
            onChanged={() => data.reload()}
            page={Math.floor(offset / DB_PAGE_SIZE) + 1}
            onPrev={() => setOffset(value => Math.max(0, value - DB_PAGE_SIZE))}
            onNext={() => setOffset(value => value + DB_PAGE_SIZE)}
          />
        )}
      </div>

      <p
        className="animate-fade-up text-xs leading-relaxed text-ink-400"
        style={delayStyle(2, 60, 240)}
      >
        {t('admin.dbHint')}
      </p>

      <div className="animate-fade-up" style={delayStyle(3, 60, 240)}>
        <AuditList />
      </div>
    </div>
  )
}

function TableData({
  data,
  onChanged,
  page,
  onPrev,
  onNext,
}: {
  data: DbTableData
  onChanged: () => void
  page: number
  onPrev: () => void
  onNext: () => void
}) {
  const { t } = useI18n()
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState('')
  const [deleting, setDeleting] = useState<Record<string, unknown> | null>(null)

  const columns = useMemo(
    () => data.columns.filter(column => column.name !== '_rowid'),
    [data.columns],
  )
  const maxPage = Math.max(1, Math.ceil(data.total / DB_PAGE_SIZE))

  function startEdit(row: Record<string, unknown>) {
    setEditing(Number(row._rowid))
    setDraft(
      Object.fromEntries(columns.map(column => [column.name, cellText(row[column.name])])),
    )
    setFailure('')
  }

  async function save(rowid: number) {
    setBusy(true)
    setFailure('')
    try {
      const values: Record<string, unknown> = {}
      for (const column of columns) {
        if (column.protected) continue
        values[column.name] = coerce(draft[column.name] ?? '', column.type)
      }
      await api.adminUpdateRow(data.table, rowid, values)
      setEditing(null)
      onChanged()
    } catch (err) {
      setFailure(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      {failure && <ErrorBox message={failure} />}

      {deleting && (
        <ConfirmBar
          message={`${t('common.delete')} ${data.table} #${String(deleting._rowid)}？`}
          confirmLabel={t('common.confirmDelete')}
          busyLabel={t('common.deleting')}
          cancelLabel={t('common.cancel')}
          busy={busy}
          onCancel={() => setDeleting(null)}
          onConfirm={async () => {
            setBusy(true)
            setFailure('')
            try {
              await api.adminDeleteRow(data.table, Number(deleting._rowid))
              setDeleting(null)
              onChanged()
            } catch (err) {
              setFailure(err instanceof Error ? err.message : String(err))
            } finally {
              setBusy(false)
            }
          }}
        />
      )}

      {data.rows.length === 0 ? (
        <Empty title={t('admin.dbEmpty')} className="py-10" />
      ) : (
        // 横向滚动：`history` 有十来个列，收窄了会挤成一团。
        // 表头 sticky，滚到下面还知道哪一列是什么。
        <div className="overflow-x-auto rounded-xl border border-paper-200">
          <table className="w-full min-w-max border-collapse text-sm">
            <thead>
              <tr className="bg-paper-200/60">
                <th className="sticky left-0 z-10 bg-paper-200/60 px-3 py-2 text-left text-xs font-medium text-ink-500">
                  rowid
                </th>
                {columns.map(column => (
                  <th
                    key={column.name}
                    className="px-3 py-2 text-left text-xs font-medium text-ink-500"
                  >
                    <span className="font-mono">{column.name}</span>
                    <span className="ml-1 text-ink-300">{column.type}</span>
                    {column.protected && (
                      <Badge tone="neutral" className="ml-1.5">
                        {t('admin.dbProtected')}
                      </Badge>
                    )}
                  </th>
                ))}
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {data.rows.map(row => {
                const rowid = Number(row._rowid)
                const isEditing = editing === rowid
                return (
                  <tr key={rowid} className="border-t border-paper-200/70 hover:bg-paper-100/50">
                    <td className="sticky left-0 z-10 bg-paper-50 px-3 py-1.5 font-mono text-xs text-ink-300 tabular-nums">
                      {rowid}
                    </td>
                    {columns.map(column => (
                      <td key={column.name} className="max-w-[22rem] px-3 py-1.5 align-top">
                        {isEditing && !column.protected ? (
                          <input
                            value={draft[column.name] ?? ''}
                            aria-label={column.name}
                            onChange={event =>
                              setDraft(current => ({ ...current, [column.name]: event.target.value }))
                            }
                            className="w-full min-w-24 rounded border border-paper-300 bg-paper-50 px-1.5 py-1 text-xs text-ink-900 outline-none focus:border-cinnabar-400"
                          />
                        ) : (
                          <span
                            className={`block truncate font-mono text-xs ${
                              column.protected
                                ? 'text-ink-300'
                                : row[column.name] === null
                                  ? 'italic text-ink-300'
                                  : 'text-ink-700'
                            }`}
                            title={cellText(row[column.name])}
                          >
                            {cellText(row[column.name])}
                          </span>
                        )}
                      </td>
                    ))}
                    <td className="whitespace-nowrap px-3 py-1.5 text-right">
                      {isEditing ? (
                        <span className="flex gap-1">
                          <Button size="sm" loading={busy} onClick={() => void save(rowid)}>
                            {t('common.save')}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={busy}
                            onClick={() => setEditing(null)}
                          >
                            {t('common.cancel')}
                          </Button>
                        </span>
                      ) : (
                        <span className="flex gap-1">
                          <Button size="sm" variant="ghost" onClick={() => startEdit(row)}>
                            {t('common.edit')}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-ink-400 hover:text-cinnabar-600"
                            onClick={() => setDeleting(row)}
                          >
                            {t('common.delete')}
                          </Button>
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center gap-3 text-xs text-ink-400">
        <Button size="sm" variant="ghost" disabled={page <= 1} onClick={onPrev}>
          {t('admin.prev')}
        </Button>
        <span className="tabular-nums">
          {t('admin.pageOf', { page })} / {maxPage} · {t('admin.dbRows', { count: data.total })}
        </span>
        <Button size="sm" variant="ghost" disabled={page >= maxPage} onClick={onNext}>
          {t('admin.next')}
        </Button>
      </div>
    </div>
  )
}

/** 最近的后台操作。写操作一条不落，读操作不记（否则这张表会被翻页记录淹掉）。 */
function AuditList() {
  const { t } = useI18n()
  const { data, error, loading } = useAsync(() => api.adminAudit(30), [])

  if (loading) return <Loading />
  if (error) return <ErrorBox message={error} />
  const rows: AuditEntry[] = data ?? []

  return (
    <div>
      <h2 className="mb-2 font-serif text-base font-semibold text-ink-800">
        {t('admin.auditTitle')}
      </h2>
      {rows.length === 0 ? (
        <Empty title={t('admin.auditEmpty')} className="py-8" />
      ) : (
        <Card className="divide-y divide-paper-200/70 p-0">
          {rows.map(row => (
            <div key={row.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 px-4 py-2">
              <span className="text-xs text-ink-300 tabular-nums">
                {shortTime(row.created_at)}
              </span>
              <span className="text-sm text-ink-700">
                {ACTION_LABEL[row.action] ?? row.action}
              </span>
              <span className="font-mono text-xs text-ink-400">{row.target}</span>
              {row.detail && (
                <span className="min-w-0 flex-1 truncate text-xs text-ink-400" title={row.detail}>
                  {row.detail}
                </span>
              )}
              <span className="ml-auto text-xs text-ink-300">#{row.user_id ?? '-'}</span>
            </div>
          ))}
        </Card>
      )}
    </div>
  )
}

/**
 * 文本框 → 数据库值。
 *
 * 为什么不能一律当字符串送：SQLite 的列亲和性虽然会把 `"1"` 往 INTEGER 上转，
 * 但**只在能无损转换时才转**，而 `meta.value` 这类 TEXT 列本来就该存字符串。
 * 按列类型决定更可控，也避免把 `"007"` 这种前导零的文本悄悄变成 `7`。
 */
function coerce(text: string, columnType: string): string | number | null {
  const type = (columnType || '').toUpperCase()
  if (type.includes('INT') || type.includes('REAL') || type.includes('NUM') || type.includes('DEC')) {
    const trimmed = text.trim()
    if (trimmed === '') return null
    const value = Number(trimmed)
    if (Number.isFinite(value)) return value
  }
  return text
}

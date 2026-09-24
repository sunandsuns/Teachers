import type { MessageKey } from '../../i18n'

/** 后台的四个页签。顺序就是"从概览到具体"的顺序。 */
export const ADMIN_TABS = ['overview', 'review', 'users', 'db'] as const
export type AdminTab = (typeof ADMIN_TABS)[number]

export const TAB_KEY: Record<AdminTab, MessageKey> = {
  overview: 'admin.tab.overview',
  review: 'admin.tab.review',
  users: 'admin.tab.users',
  db: 'admin.tab.db',
}

/** 数据库浏览一页多少行。与后端 `MAX_ROWS=200` 留出余量。 */
export const DB_PAGE_SIZE = 25

/**
 * 审计动作名 → 中文说法。
 *
 * 后端存的是机器可读的动词（`update_row`、`approve_book`…），
 * 直接显示给管理员看等于让他读代码。这张表是**展示层**的翻译，
 * 认不出的动作原样显示——将来后端加了新动作，界面不会因此报错。
 */
export const ACTION_LABEL: Record<string, string> = {
  set_admin: '调整管理员',
  reset_password: '重置密码',
  delete_user: '删除用户',
  approve_book: '批准公开',
  reject_book: '驳回公开',
  remove_public: '撤下公共书',
  update_row: '修改数据行',
  insert_row: '新增数据行',
  delete_row: '删除数据行',
}

/** 字节数 → 人看的短串。数据库文件几百 KB 到几十 MB，不用做到 GB 那一档。 */
export function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** 把后端返回的时间戳（ISO 8601）截成 `MM-DD HH:mm`，列表里够用。 */
export function shortTime(iso: string): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** 单元格值的显示。`null` 与空串在数据库里是两回事，界面上也要能分清。 */
export function cellText(value: unknown): string {
  if (value === null) return 'NULL'
  if (value === undefined) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

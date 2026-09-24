import { Card } from '../../components/ui'
import { useI18n } from '../../i18n'
import type { AdminOverview } from '../../api/client'
import { delayStyle } from '../../lib/motion'
import { formatBytes } from './constants'

/** 一个数字 + 一行说明。整块可点的地方不在这里，所以纯展示。 */
function Stat({
  index,
  label,
  value,
  hint,
}: {
  /** 在这一屏里的位置，用来错峰入场。 */
  index: number
  label: string
  value: string
  hint?: string
}) {
  return (
    <Card className="animate-rise p-4" style={delayStyle(index, 40, 240)}>
      <p className="text-xs text-ink-400">{label}</p>
      <p className="mt-1 font-serif text-2xl font-bold tabular-nums text-ink-900">{value}</p>
      {hint && <p className="mt-0.5 truncate text-xs text-ink-400">{hint}</p>}
    </Card>
  )
}

/**
 * 总览。
 *
 * 排布按"管理员最先想知道什么"来：**今天发生了什么**（今日问答、今日新增、
 * 待审核）在最前面，其次是存量规模，最后才是数据库本身。
 *
 * 待审核那块数字为 0 时不着色——一个常年显示红色的 0 会让人对红色麻木。
 *
 * 十二张卡**逐张错峰**入场（40ms 一张，最多 240ms），和「新书审核」「用户」
 * 两个分页里逐行入场的节奏对齐。四个分页切过来切过去时，入场方式一致，
 * 才不会有一页"啪"地整块出现、另一页一张张来。
 *
 * 用行内 `style` 传延迟而不是给每个下标写一个类：Tailwind 扫不到运行时算出来的
 * 类名，而且为 0..11 各写一条 `delay-[40ms]` 是纯噪音。延迟是**数据**，走 style。
 */
export default function OverviewPanel({ data }: { data: AdminOverview }) {
  const { t } = useI18n()

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat index={0} label={t('admin.stat.historyToday')} value={String(data.history_today)} />
        <Stat index={1} label={t('admin.stat.shelfToday')} value={String(data.shelf_books_today)} />
        <Stat
          index={2}
          label={t('admin.stat.pending')}
          value={String(data.pending_review)}
          hint={data.pending_review > 0 ? t('admin.tab.review') : undefined}
        />
        <Stat index={3} label={t('admin.stat.public')} value={String(data.public_contributions)} />
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat index={4} label={t('admin.stat.users')} value={String(data.users)} />
        <Stat index={5} label={t('admin.stat.admins')} value={String(data.admins)} />
        <Stat index={6} label={t('admin.stat.history')} value={String(data.history)} />
        <Stat index={7} label={t('admin.stat.shelf')} value={String(data.shelf_books)} />
        <Stat index={8} label={t('admin.stat.traits')} value={String(data.traits)} />
        <Stat index={9} label={t('admin.stat.sessions')} value={String(data.sessions)} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Card className="animate-rise p-4" style={delayStyle(10, 40, 240)}>
          <p className="text-xs text-ink-400">{t('admin.corpus')}</p>
          <p className="mt-1 font-serif text-lg font-semibold text-ink-900">
            {t('admin.corpusValue', {
              books: data.corpus_books,
              chapters: data.corpus_chapters,
            })}
          </p>
          <p className="mt-0.5 line-clamp-1 text-xs text-ink-400">
            {data.corpus_categories.join(' / ')}
          </p>
        </Card>
        <Card className="animate-rise p-4" style={delayStyle(11, 40, 240)}>
          <p className="text-xs text-ink-400">{t('admin.storage')}</p>
          <p className="mt-1 font-serif text-lg font-semibold text-ink-900">
            {t('admin.storageValue', {
              size: formatBytes(data.db_bytes),
              tables: data.tables,
            })}
          </p>
          {/* 完整路径用 title 挂上：它很长，铺开会把版面撑破，
              但排查问题时又确实需要它 */}
          <p className="mt-0.5 truncate text-xs text-ink-400" title={data.db_path}>
            {data.db_path}
          </p>
        </Card>
      </div>
    </div>
  )
}

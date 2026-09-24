import type { HistoryStatus } from '../../api/client'
import { useI18n } from '../../i18n'
import { formatDay } from './format'

/** 分隔点。用元素而不是文字里的 `·`，是为了让三个数据各自成为**独立的文本节点**——
 *  读屏会把它们分开念，测试里也能按单条断言。 */
function Dot() {
  return (
    <span aria-hidden="true" className="text-paper-400">
      ·
    </span>
  )
}

/**
 * 存储概况：有多少条、留多久、下次何时清理，以及库文件在哪儿。
 *
 * 这一行的职责不只是"报数"，还要让人**放心**：知道记录不会无限堆积、
 * 知道想备份或彻底删掉时去哪儿找。所以库路径单独一行、等宽字体、可折行——
 * 它是个要被人抄走的东西，不能藏在句子中间。
 */
export default function StatusLine({ status }: { status: HistoryStatus }) {
  const { lang, t } = useI18n()

  return (
    <div className="mb-6 rounded-lg border border-paper-200/70 bg-paper-50/70 px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-600">
        <span>{t('history.total', { count: status.total })}</span>
        <Dot />
        <span>{t('history.retention', { days: Math.round(status.retention_days) })}</span>
        <Dot />
        <span>{t('history.nextPurge', { day: formatDay(status.next_purge_at, t, lang) })}</span>
      </div>
      <p className="mt-1 break-all font-mono text-xs text-ink-400">
        {t('history.dbPath', { path: status.db_path })}
      </p>
    </div>
  )
}

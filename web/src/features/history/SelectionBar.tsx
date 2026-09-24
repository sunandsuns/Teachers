import { Button } from '../../components/ui'
import { useI18n } from '../../i18n'

/**
 * 选择模式的工具条：报数 + 全选 / 删除选中。
 *
 * 两个刻意的设计：
 *
 * 1. **没勾中也让点「删除选中」**。点下去会得到一句"还没勾选要删的内容"。
 *    灰着按钮虽然"正确"，但在用户眼里就是"点了没反应"——那比一句提示糟糕得多。
 * 2. **报数只在有勾选时出现**，没勾时显示"勾选要删的内容"当引导语。
 *    "已选 0 个话题 · 0 条记录"读起来像故障码。
 */
export default function SelectionBar({
  pickedTopics,
  pickedRecords,
  pickedCount,
  allPicked,
  busy,
  onToggleAll,
  onDelete,
}: {
  pickedTopics: number
  pickedRecords: number
  pickedCount: number
  allPicked: boolean
  busy: boolean
  onToggleAll: () => void
  onDelete: () => void
}) {
  const { t } = useI18n()

  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-paper-300/70 bg-paper-50 px-4 py-2.5 shadow-card animate-drop-in">
      <span className="text-sm text-ink-600">
        {pickedCount > 0
          ? t('history.pickedCount', { topics: pickedTopics, records: pickedRecords })
          : t('history.pickedNone')}
      </span>
      <span className="ml-auto flex items-center gap-1">
        <Button variant="ghost" size="sm" onClick={onToggleAll} disabled={busy}>
          {allPicked ? t('history.selectNone') : t('history.selectAll')}
        </Button>
        <Button variant="secondary" size="sm" onClick={onDelete} disabled={busy}>
          {t('history.deleteSelected')}
        </Button>
      </span>
    </div>
  )
}

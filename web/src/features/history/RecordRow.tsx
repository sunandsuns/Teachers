import type { HistoryItem } from '../../api/client'
import Markdown from '../../components/Markdown'
import { Button } from '../../components/ui'
import { useI18n } from '../../i18n'
import { formatTime } from './format'

/** 出处信息之间的分隔点。用元素而非文字，方便读屏逐个念、测试逐条断言。 */
function Dot() {
  return <span aria-hidden="true" className="h-1 w-1 rounded-full bg-paper-400" />
}

/**
 * 段内的一条问答：问题、回答、出处信息、以及两个动作。
 *
 * 勾选框只在"选择模式 + 本段未被整段勾中"时出现。整段勾中之后段内每条
 * 注定一起走，再给框只会让人怀疑"我是不是漏了哪一条"——想只删其中一条，
 * 得先取消整段的勾选。这条规则由 `useSelection` 保证，这里只负责如实渲染。
 */
export default function RecordRow({
  record,
  selecting,
  picked,
  onPick,
  onAskAgain,
  onDelete,
}: {
  record: HistoryItem
  selecting: boolean
  picked: boolean
  onPick: () => void
  onAskAgain: () => void
  onDelete: () => void
}) {
  const { lang, t } = useI18n()

  return (
    <div className="flex items-start gap-2.5">
      {selecting && (
        <label className="shrink-0 cursor-pointer pt-1">
          <input
            type="checkbox"
            className="block h-4 w-4 cursor-pointer accent-cinnabar-600"
            checked={picked}
            onChange={onPick}
            aria-label={t('history.pickRecord', { question: record.question })}
          />
        </label>
      )}

      <div className="min-w-0 flex-1 space-y-2">
        <p className="break-words font-serif text-sm font-bold leading-relaxed text-ink-900">
          {record.question}
        </p>

        <Markdown content={record.answer} />

        <div className="flex flex-wrap items-center gap-2 border-t border-paper-200 pt-2 text-xs text-ink-400">
          <span>{formatTime(record.created_ts, t, lang)}</span>
          <Dot />
          <span>{t('history.cited', { count: record.retrieved_count })}</span>
          <Dot />
          {/* 两种作答模式如实区分：本地检索和 AI 解读不是一回事，
              用户有权知道自己看的是哪一种 */}
          <span>
            {record.llm_used
              ? t('history.aiAnswer', { model: record.model ?? '' })
              : t('history.localMode')}
          </span>

          <span className="ml-auto flex items-center gap-1">
            {/* 带上话题一起跳过去：接着问的问题仍归在这件事下 */}
            <Button variant="ghost" size="sm" onClick={onAskAgain}>
              {t('history.askAgain')}
            </Button>
            <Button variant="ghost" size="sm" onClick={onDelete}>
              {t('history.delete')}
            </Button>
          </span>
        </div>
      </div>
    </div>
  )
}

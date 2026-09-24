import type { HistoryItem, TopicItem } from '../../api/client'
import { Button, Spinner } from '../../components/ui'
import { useI18n } from '../../i18n'
import { formatTime, preview } from './format'
import RecordRow from './RecordRow'

/** 展开箭头。转 180° 而不是换成另一个图标——连续的变化比跳变更容易读懂。 */
function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      fill="none"
      className={`h-3.5 w-3.5 shrink-0 transition-transform duration-calm ease-spring ${
        open ? 'rotate-180' : ''
      }`}
    >
      <path
        d="M4 6.5 8 10.5l4-4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * 一张话题卡：一次会话里的连续追问算一个话题。
 *
 * 平铺的列表追问几轮就没法看了——同一件事会散成好几条，每条再贴一遍整篇回答。
 * 所以收起时只给**标题 + 时间 + 一段预览**，点开才展开那段对话。
 * 预览是必须的：不点开也能想起"这件事聊到哪了"，否则列表就只是一串标题。
 *
 * 两处结构上的讲究：
 *
 * - **勾选框在标题按钮外面**。`input` 不能嵌在 `button` 里，那是无效 HTML，
 *   浏览器会把 DOM 拆开，React 随后就会对不上。
 * - **标题与预览各自是独立的文本节点**（各自包一个元素）。读屏会把它们分开念，
 *   也让"卡片标题"这件事在无障碍树里站得住。
 */
export default function TopicCard({
  topic,
  records,
  open,
  opening,
  selecting,
  topicPicked,
  pickedRecords,
  onToggle,
  onPickTopic,
  onPickRecord,
  onAskAgain,
  onDeleteRecord,
  onDeleteTopic,
}: {
  topic: TopicItem
  records: HistoryItem[]
  open: boolean
  opening: boolean
  selecting: boolean
  topicPicked: boolean
  pickedRecords: ReadonlySet<number>
  onToggle: () => void
  onPickTopic: () => void
  onPickRecord: (id: number) => void
  onAskAgain: (record: HistoryItem) => void
  onDeleteRecord: (id: number) => void
  onDeleteTopic: () => void
}) {
  const { lang, t } = useI18n()

  return (
    <article className="card group relative">
      {/* 左缘的朱砂竖线：展开时立起来，收起时悬停才立。整张卡片因此有了
          "这一段是打开的"的即时信号，而代价只是一个 transform。 */}
      <span
        aria-hidden="true"
        className={`absolute inset-y-4 left-0 w-[3px] origin-top rounded-full bg-cinnabar-500 transition-transform duration-slow ease-spring ${
          open ? 'scale-y-100' : 'scale-y-0 group-hover:scale-y-100'
        }`}
      />

      <div className="flex items-start">
        {selecting && (
          <label className="shrink-0 cursor-pointer pl-5 pr-1 pt-5">
            <input
              type="checkbox"
              className="block h-4 w-4 cursor-pointer accent-cinnabar-600"
              checked={topicPicked}
              onChange={onPickTopic}
              aria-label={t('history.pickTopic', { title: topic.title })}
            />
          </label>
        )}

        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="min-w-0 flex-1 px-5 py-4 text-left"
        >
          <span className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
            <span className="min-w-0 break-words font-serif text-base font-bold leading-relaxed text-ink-900 transition-colors duration-quick group-hover:text-cinnabar-600">
              {topic.title}
            </span>
            <span className="shrink-0 pt-0.5 text-xs text-ink-400">
              {formatTime(topic.last_ts, t, lang)}
            </span>
          </span>

          {/* 收起时给一段预览：不点开也能想起这件事聊到哪了 */}
          {!open && (
            <span className="mt-2 block text-sm leading-relaxed text-ink-500">
              {preview(topic.latest_answer)}
            </span>
          )}

          <span className="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-400">
            <span>{t('history.topicTurns', { count: topic.question_count })}</span>
            <span aria-hidden="true" className="h-1 w-1 rounded-full bg-paper-400" />
            <span>{open ? t('history.collapse') : t('history.expand')}</span>
            <Chevron open={open} />
          </span>
        </button>
      </div>

      {open && (
        // .unfold 用 grid-template-rows 从 0fr 长到 1fr——高度由内容决定、算不出来，
        // 交给浏览器插值，比测 scrollHeight 或猜 max-height 都稳
        <div className="unfold">
          <div>
            <div className="mx-5 border-t border-paper-200 pb-5 pt-4">
              {opening && (
                <div className="flex items-center gap-2.5 py-2">
                  <Spinner size="sm" />
                  <span className="text-sm text-ink-500">{t('history.loadingTopic')}</span>
                </div>
              )}

              <div className="space-y-5">
                {records.map(record => (
                  <RecordRow
                    key={record.id}
                    record={record}
                    /* 整段已勾中就整段一起走，段内每条不再单独给框 */
                    selecting={selecting && !topicPicked}
                    picked={pickedRecords.has(record.id)}
                    onPick={() => onPickRecord(record.id)}
                    onAskAgain={() => onAskAgain(record)}
                    onDelete={() => onDeleteRecord(record.id)}
                  />
                ))}
              </div>

              <div className="mt-4 flex justify-end">
                <Button variant="ghost" size="sm" onClick={onDeleteTopic}>
                  {t('history.deleteTopic')}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </article>
  )
}

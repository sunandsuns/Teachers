import { useState } from 'react'
import { api, type PublicBookRow, type ReviewRow } from '../../api/client'
import Markdown from '../../components/Markdown'
import { Badge, Button, Card, Collapse, ConfirmBar, Empty } from '../../components/ui'
import { ErrorBox, Loading } from '../../components/Status'
import { useAsync } from '../../hooks/useAsync'
import { useI18n } from '../../i18n'
import { shortTime } from './constants'

interface ReviewPanelProps {
  rows: ReviewRow[] | null
  loading: boolean
  error: string | null
  /** 审完之后让上层重新拉一遍队列与总览 */
  onChanged: () => void
}

/**
 * 新书审核。
 *
 * 这是"用户加的书要不要进公共书架"的那个决定点。两块内容：
 *   1. **待审队列**——用户申请公开的书，先进先出
 *   2. **已上架的贡献**——批错了能撤回（撤下之后原作者的可见性退回 private）
 *
 * 批准时要填分类：公共书架的书目是按类目分组的（`BookSummary.category`），
 * 留空会归到「其他」。这一格给默认值而不是必填，是因为管理员未必知道这本书
 * 该归哪一类，而"先放进去、以后再改"比"卡在这里批不了"更实际。
 *
 * 驳回要填原因，且**这个原因作者看得到**（在「我的书架」那张卡片上）。
 * 所以占位文字里明说了这一点——不写清楚，管理员会以为这只是给自己看的备注。
 */
export default function ReviewPanel({ rows, loading, error, onChanged }: ReviewPanelProps) {
  const { t } = useI18n()
  const [busy, setBusy] = useState<number | null>(null)
  const [failure, setFailure] = useState('')

  if (error) return <ErrorBox message={error} />
  if (loading) return <Loading />

  const queue = rows ?? []

  return (
    <div className="space-y-6">
      {failure && <ErrorBox message={failure} />}

      {queue.length === 0 ? (
        <Empty title={t('admin.reviewEmpty')} hint={t('admin.reviewEmptyHint')} />
      ) : (
        <div className="space-y-3">
          {queue.map((row, index) => (
            <ReviewCard
              key={row.id}
              row={row}
              index={index}
              busy={busy === row.id}
              onDone={message => {
                if (message) setFailure(message)
                onChanged()
              }}
              onBusy={setBusy}
            />
          ))}
        </div>
      )}

      <PublicList onChanged={onChanged} />
    </div>
  )
}

function ReviewCard({
  row,
  index,
  busy,
  onDone,
  onBusy,
}: {
  row: ReviewRow
  index: number
  busy: boolean
  onDone: (message: string) => void
  onBusy: (id: number | null) => void
}) {
  const { t } = useI18n()
  const [note, setNote] = useState('')
  const [category, setCategory] = useState('')
  const [showGuide, setShowGuide] = useState(false)

  async function decide(approve: boolean) {
    onBusy(row.id)
    onDone('')
    try {
      await api.adminReview(row.id, approve, note.trim(), category.trim())
    } catch (err) {
      onDone(err instanceof Error ? err.message : String(err))
    } finally {
      onBusy(null)
    }
  }

  return (
    <Card className="p-4 animate-rise" style={{ animationDelay: `${Math.min(index, 12) * 40}ms` }}>
      <div className="flex gap-4">
        {row.cover_url ? (
          <img
            src={row.cover_url}
            alt=""
            loading="lazy"
            className="h-24 w-16 shrink-0 rounded object-cover shadow-card"
          />
        ) : (
          <div
            aria-hidden="true"
            className="flex h-24 w-16 shrink-0 items-center justify-center rounded bg-paper-200/70 font-serif text-lg text-ink-300"
          >
            {row.title.slice(0, 1)}
          </div>
        )}

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
            <div className="min-w-0">
              <h3 className="font-serif text-base font-semibold leading-snug text-ink-900">
                {row.title}
              </h3>
              <p className="mt-0.5 text-xs text-ink-500">
                {[row.author || t('shelf.unknownAuthor'), row.year].filter(Boolean).join(' · ')}
              </p>
            </div>
            <Badge tone="neutral">{shortTime(row.created_at)}</Badge>
          </div>

          <p className="mt-1.5 text-xs text-ink-400">{t('admin.from', { email: row.user_email })}</p>

          {row.summary && (
            <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-ink-600">
              {row.summary}
            </p>
          )}

          {row.subjects.length > 0 && (
            <p className="mt-1 line-clamp-1 text-xs text-ink-400">
              {row.subjects.slice(0, 6).join(' / ')}
            </p>
          )}

          {row.has_guide && (
            <div className="mt-2">
              <button
                type="button"
                onClick={() => setShowGuide(value => !value)}
                aria-expanded={showGuide}
                className="text-xs font-medium text-cinnabar-600 transition-colors duration-quick hover:text-cinnabar-700"
              >
                {showGuide ? t('shelf.guideHide') : t('shelf.guideShow')}
              </button>
              {showGuide && (
                <Collapse className="mt-2 rounded-lg border border-paper-200 bg-paper-50/70 px-3.5 py-2.5">
                  <Markdown content={row.guide} />
                </Collapse>
              )}
            </div>
          )}

          <div className="mt-3 flex flex-wrap gap-2">
            <input
              value={category}
              onChange={event => setCategory(event.target.value)}
              placeholder={t('admin.categoryPlaceholder')}
              aria-label={t('admin.categoryPlaceholder')}
              className="min-w-0 flex-1 basis-32 rounded-lg border border-paper-300 bg-paper-50 px-2.5 py-1.5 text-sm text-ink-900 outline-none transition-[border-color,box-shadow] duration-quick placeholder:text-ink-300 focus:border-cinnabar-400 focus:ring-2 focus:ring-cinnabar-500/15"
            />
            <input
              value={note}
              onChange={event => setNote(event.target.value)}
              placeholder={t('admin.notePlaceholder')}
              aria-label={t('admin.notePlaceholder')}
              className="min-w-0 flex-1 basis-40 rounded-lg border border-paper-300 bg-paper-50 px-2.5 py-1.5 text-sm text-ink-900 outline-none transition-[border-color,box-shadow] duration-quick placeholder:text-ink-300 focus:border-cinnabar-400 focus:ring-2 focus:ring-cinnabar-500/15"
            />
          </div>

          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <Button size="sm" loading={busy} onClick={() => void decide(true)}>
              {t('admin.approve')}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={() => void decide(false)}
            >
              {t('admin.reject')}
            </Button>
          </div>
        </div>
      </div>
    </Card>
  )
}

/** 已上架的贡献。批错了能从这里撤回。 */
function PublicList({ onChanged }: { onChanged: () => void }) {
  const { t } = useI18n()
  const { data, error, loading, reload } = useAsync(() => api.adminPublicBooks(), [])
  const [pending, setPending] = useState<PublicBookRow | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState('')

  if (loading) return <Loading />
  if (error) return <ErrorBox message={error} />
  const rows = data ?? []

  return (
    <div>
      <h2 className="mb-3 font-serif text-base font-semibold text-ink-800">
        {t('admin.publicTitle')}
      </h2>
      {failure && <ErrorBox message={failure} />}
      {rows.length === 0 ? (
        <Empty title={t('admin.publicEmpty')} className="py-10" />
      ) : (
        <div className="space-y-2">
          {rows.map(row => (
            <Card key={row.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 p-3">
              <span className="font-mono text-xs text-ink-400">{row.book_id}</span>
              <span className="min-w-0 flex-1 truncate font-serif text-sm text-ink-800">
                《{row.title}》
                <span className="ml-2 text-xs text-ink-400">{row.author}</span>
              </span>
              <span className="text-xs text-ink-400">{row.category}</span>
              <Button
                size="sm"
                variant="ghost"
                className="text-ink-400 hover:text-cinnabar-600"
                onClick={() => setPending(row)}
              >
                {t('admin.removePublic')}
              </Button>
            </Card>
          ))}
        </div>
      )}

      {pending && (
        <div className="mt-3">
          <ConfirmBar
            message={`${t('admin.removePublic')}《${pending.title}》？`}
            confirmLabel={t('common.confirmDelete')}
            busyLabel={t('common.deleting')}
            cancelLabel={t('common.cancel')}
            busy={busy}
            onCancel={() => setPending(null)}
            onConfirm={async () => {
              setBusy(true)
              setFailure('')
              try {
                await api.adminRemovePublic(pending.id)
                setPending(null)
                reload()
                // 上层那份总览里的"公共贡献"计数也变了
                onChanged()
              } catch (err) {
                setFailure(err instanceof Error ? err.message : String(err))
              } finally {
                setBusy(false)
              }
            }}
          />
        </div>
      )}
    </div>
  )
}

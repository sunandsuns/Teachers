import { useState } from 'react'
import type { ShelfBook, ShelfStatus, ShelfVisibility } from '../../api/client'
import Markdown from '../../components/Markdown'
import { Badge, Button, Card, Chip, Collapse, ConfirmBar } from '../../components/ui'
import { SkeletonText } from '../../components/ui/Skeleton'
import { useI18n } from '../../i18n'
import { STATUS_KEY, STATUS_ORDER, VISIBILITY_KEY } from './constants'

interface ShelfBookCardProps {
  book: ShelfBook
  /** 在兄弟序列里的位置，用于错峰入场 */
  index: number
  /** 这本书的导读正在手动重新生成 */
  regenerating: boolean
  onChangeStatus: (book: ShelfBook, status: ShelfStatus) => Promise<unknown>
  onRemove: (book: ShelfBook) => Promise<unknown>
  onSubmit: (book: ShelfBook) => Promise<unknown>
  onCancelReview: (book: ShelfBook) => Promise<unknown>
  onRegenerate: (book: ShelfBook) => Promise<unknown>
}

/** 可见性标记的色调：只有"已公开"是好事（朱砂），"待审核"是等待（中性偏暖）。 */
const TONE: Record<ShelfVisibility, 'brand' | 'neutral' | 'celadon'> = {
  private: 'neutral',
  pending: 'brand',
  public: 'celadon',
  rejected: 'neutral',
}

/**
 * 书架上的一本书。
 *
 * 版面按"用户此刻最可能想干什么"排：书名 → 状态 → 导读 → 别的动作。
 *
 * - **书名就是阅读入口**。书架上的书没有正文（联网检索只拿得到书名、作者、
 *   封面、简介），导读是它唯一能读的东西——所以有导读时书名可点，点开就是
 *   正文。没导读时书名保持纯文本：一个点了没反应的可点标题，比一个不能点的
 *   标题更让人困惑，而这个页面原先正是这么表现的（用户的原话是"检索出来了
 *   但是不给读，我点不了"）。
 * - **状态药丸**（想读/在读/读过）放在最上面且一直可见：这是这个页面上
 *   最高频的动作，收进菜单里等于每次多两次点击。
 * - **导读默认收起**。它可能有一两千字，展开会把列表撑得没法扫；而"我加了
 *   哪些书"才是这一页的主要问题。收起时给一行预览，让人知道里面有没有东西。
 * - **没导读时要说清两件事**：出过什么事（`guide_error`），以及这本书本来
 *   就没有正文、导读是唯一能读的。少说任何一件，用户都只能干等。
 * - **删除走就地确认条**，不用 `window.confirm`（理由见 `ConfirmBar`）。
 * - **申请公开**只在 `private` / `rejected` 时出现。已经公开或正在审核的书，
 *   再点一次没有任何意义，摆着只会让人怀疑是不是漏点了。
 */
export default function ShelfBookCard({
  book,
  index,
  regenerating,
  onChangeStatus,
  onRemove,
  onSubmit,
  onCancelReview,
  onRegenerate,
}: ShelfBookCardProps) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  async function run(label: string, action: () => Promise<unknown>) {
    setBusy(label)
    setError('')
    try {
      await action()
      return true
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      return false
    } finally {
      setBusy('')
    }
  }

  const canSubmit = book.visibility === 'private' || book.visibility === 'rejected'
  const toggleGuide = () => setOpen(value => !value)

  return (
    <Card
      className="p-4 animate-rise"
      // 错峰入场：同屏十几张卡片一起淡入会显得很"糊"，
      // 每张晚 40ms 就有"依次落位"的层次。超过十来张之后不再加延迟，
      // 否则列表末尾要等一秒才出现。
      style={{ animationDelay: `${Math.min(index, 12) * 40}ms` }}
    >
      <div className="flex gap-4">
        <Cover book={book} />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
            <div className="min-w-0">
              <h3 className="font-serif text-base font-semibold leading-snug text-ink-900">
                {/* 有导读才把书名变成按钮。**别给它加 aria-label**：标题的
                    可访问名是从子节点算出来的，按钮上另写一个名字会把
                    `heading[name="书名"]` 一起改掉（测试与读屏都按那个找）。 */}
                {book.has_guide ? (
                  <button
                    type="button"
                    onClick={toggleGuide}
                    aria-expanded={open}
                    className="rounded-sm text-left transition-colors duration-quick hover:text-cinnabar-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar-500/25"
                  >
                    {book.title}
                  </button>
                ) : (
                  book.title
                )}
              </h3>
              <p className="mt-0.5 text-xs text-ink-500">
                {[book.author || t('shelf.unknownAuthor'), book.year].filter(Boolean).join(' · ')}
              </p>
            </div>
            <Badge tone={TONE[book.visibility]}>{t(VISIBILITY_KEY[book.visibility])}</Badge>
          </div>

          {book.visibility === 'rejected' && book.review_note && (
            <p className="mt-2 rounded-sm bg-paper-200/70 px-2.5 py-1.5 text-xs leading-relaxed text-ink-600">
              {t('shelf.rejectNote', { note: book.review_note })}
            </p>
          )}

          {/* 阅读状态：三个互斥开关。用 Chip 而不是 Segmented，
              因为 Segmented 的滑动底块在每张卡片里各算一次位置，
              长列表下会多出一堆 measure —— 药丸更轻。 */}
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            {STATUS_ORDER.map(status => (
              <Chip
                key={status}
                active={book.status === status}
                disabled={busy !== ''}
                aria-label={t('shelf.setStatus', { status: t(STATUS_KEY[status]) })}
                onClick={() => {
                  if (book.status === status) return
                  void run('status', () => onChangeStatus(book, status))
                }}
                className="px-2.5 py-1 text-xs"
              >
                {t(STATUS_KEY[status])}
              </Chip>
            ))}
          </div>

          <Guide
            book={book}
            open={open}
            onToggle={toggleGuide}
            regenerating={regenerating}
            busy={busy === 'guide'}
            onRegenerate={() => run('guide', () => onRegenerate(book))}
          />

          {error && (
            <p role="alert" className="mt-2 text-xs text-cinnabar-600">
              {error}
            </p>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {canSubmit ? (
              <Button
                size="sm"
                variant="secondary"
                loading={busy === 'submit'}
                onClick={() => void run('submit', () => onSubmit(book))}
              >
                {t('shelf.submit')}
              </Button>
            ) : book.visibility === 'pending' ? (
              <Button
                size="sm"
                variant="ghost"
                loading={busy === 'cancel'}
                onClick={() => void run('cancel', () => onCancelReview(book))}
              >
                {t('shelf.cancelReview')}
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="ghost"
              className="text-ink-400 hover:text-cinnabar-600"
              onClick={() => setConfirming(true)}
            >
              {t('shelf.remove')}
            </Button>
          </div>
        </div>
      </div>

      {confirming && (
        <div className="mt-3">
          <ConfirmBar
            message={`${t('shelf.remove')}《${book.title}》？`}
            confirmLabel={t('common.confirmDelete')}
            busyLabel={t('common.deleting')}
            cancelLabel={t('common.cancel')}
            busy={busy === 'remove'}
            onCancel={() => setConfirming(false)}
            onConfirm={async () => {
              const ok = await run('remove', () => onRemove(book))
              if (ok) setConfirming(false)
            }}
          />
        </div>
      )}
    </Card>
  )
}

/**
 * 导读区。
 *
 * 四种状态各有各的说法，不能共用一句话：
 *   · 有导读        → 给一行预览 + 展开按钮
 *   · 正在生成      → "生成中"，并配骨架屏（内容是**已知形状**的）
 *   · 生成失败      → 把原因摆出来 + 一个重试按钮
 *   · 从没生成过    → "还没有导读"，并说明**这本书本来就没有正文**
 *
 * 后两种原先共用「这本书还没有导读」。那句话说不出任何可执行的信息：用户不
 * 知道是失败了还是没试过，也不知道能怎么办——而失败是永久的（后台任务只跑
 * 一次，不会自己重来）。
 */
function Guide({
  book,
  open,
  onToggle,
  regenerating,
  busy,
  onRegenerate,
}: {
  book: ShelfBook
  open: boolean
  onToggle: () => void
  regenerating: boolean
  busy: boolean
  onRegenerate: () => void
}) {
  const { t } = useI18n()

  if (book.has_guide) {
    return (
      <div className="mt-3">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="group flex w-full items-baseline gap-1.5 text-left text-xs text-ink-400 transition-colors duration-quick hover:text-cinnabar-600"
        >
          {/* 收起时显示第一句当预览：让人知道里面有没有东西，
              而不是只有一个孤零零的"展开" */}
          <span className="shrink-0 font-medium text-cinnabar-600">
            {open ? t('shelf.guideHide') : t('shelf.guideShow')}
          </span>
          {!open && <span className="truncate">{preview(book.guide)}</span>}
        </button>
        {open && (
          <Collapse className="mt-2 rounded-lg border border-paper-200 bg-paper-50/70 px-3.5 py-2.5">
            <Markdown content={book.guide} />
          </Collapse>
        )}
      </div>
    )
  }

  // 刚加进来、或者刚点了"重新生成"：导读正在后台跑。用骨架屏而不是一句
  // "生成中"——内容形状是已知的（几段文字），把版式先撑出来，生成完就不会
  // 整块跳一下。
  //
  // `regenerating` 单独判：重试的那本书 `created_at` 是旧的，光看时间
  // 会落到下面分支，于是点了按钮界面毫无变化。
  //
  // 时间那一半还要再过一道 `guide_error`：它非空就说明这一轮**已经出结果了**
  // （失败也是结果）。此时继续说"生成中"是最气人的那种谎——答案早就有了，
  // 却让人对着骨架屏多等一分钟，而真实情况是他需要点一下重试。
  const fresh = Date.now() - Date.parse(book.created_at) < 60_000
  if (regenerating || (fresh && !book.guide_error)) {
    return (
      <div className="mt-3">
        <p className="mb-2 text-xs text-ink-400">{t('shelf.guidePending')}</p>
        <SkeletonText lines={2} />
      </div>
    )
  }

  return (
    <div className="mt-3">
      {book.guide_error ? (
        <p role="alert" className="mb-1 text-xs leading-relaxed text-cinnabar-600">
          {t('shelf.guideFailed', { reason: book.guide_error })}
        </p>
      ) : (
        <p className="mb-1 text-xs text-ink-300">{t('shelf.guideEmpty')}</p>
      )}
      <p className="mb-2 text-xs leading-relaxed text-ink-400">{t('shelf.guideNoText')}</p>
      <Button size="sm" variant="secondary" loading={busy} onClick={onRegenerate}>
        {book.guide_error ? t('shelf.guideRetry') : t('shelf.guideGenerate')}
      </Button>
    </div>
  )
}

/** 导读的第一句，充当收起时的预览。
 *
 * **跳过小标题**：导读是按 `## 这本书在讲什么 / ## 为什么值得读` 分段写的，
 * 拿第一行当预览就只会显示一个标题——那等于什么都没说。取第一段真正的正文。 */
function preview(guide: string): string {
  const lines = guide
    .split('\n')
    .map(text => text.trim())
    .filter(text => text.length > 0)
  const body = lines.find(text => !text.startsWith('#')) ?? lines[0] ?? ''
  return body.replace(/^[#>*\-\s]+/, '').slice(0, 40)
}

function Cover({ book }: { book: ShelfBook }) {
  if (!book.cover_url) {
    return (
      <div
        aria-hidden="true"
        className="flex h-24 w-16 shrink-0 items-center justify-center rounded bg-paper-200/70 font-serif text-lg text-ink-300"
      >
        {book.title.slice(0, 1)}
      </div>
    )
  }
  return (
    <img
      src={book.cover_url}
      alt=""
      loading="lazy"
      className="h-24 w-16 shrink-0 rounded object-cover shadow-card"
    />
  )
}

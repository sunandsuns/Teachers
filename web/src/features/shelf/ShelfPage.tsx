import { useMemo, useState } from 'react'
import type { BookCandidate, ShelfStatus } from '../../api/client'
import { ErrorBox, Loading } from '../../components/Status'
import { Chip, Empty, PageHeader } from '../../components/ui'
import { useI18n } from '../../i18n'
import BookFinder from './BookFinder'
import { STATUS_KEY, STATUS_ORDER } from './constants'
import ShelfBookCard from './ShelfBookCard'
import { useShelf } from './useShelf'

/**
 * 「我的书架」。
 *
 * 这个文件只负责**编排**：什么时候显示骨架、什么时候显示空态、按什么顺序摆。
 * 数据与动作在 `useShelf`，找书在 `BookFinder`，单本书在 `ShelfBookCard`。
 * 所以"改筛选规则"和"改卡片版式"是两件互不打扰的事。
 *
 * 三种空态要分清楚，它们的原因完全不同：
 *   · 书架为空     → 还没加过书，引导去上面的检索框
 *   · 该状态为空   → 筛选太窄了，给一条退回去的路
 *   · 加载失败     → 是错误，不是空，必须能看出来
 */
export default function ShelfPage() {
  const { t } = useI18n()
  const shelf = useShelf()
  const [notice, setNotice] = useState('')

  /** 书架上已有的 source_key。用来把检索结果里"已经加过"的那条标出来。 */
  const onShelfKeys = useMemo(
    () => new Set(shelf.books.map(book => book.source_key).filter(Boolean)),
    [shelf.books],
  )

  async function handleAdd(candidate: BookCandidate) {
    const created = await shelf.add(candidate)
    setNotice(t('shelf.addedToast', { title: created.title }))
    // 提示条自己消失。用定时器而不是"点一下关掉"：这是一条**成功**回执，
    // 不该占着用户的注意力让他专门去点。
    window.setTimeout(() => setNotice(''), 4000)
  }

  if (shelf.error && shelf.books.length === 0) {
    return <ErrorBox message={shelf.error} />
  }

  const filters: { value: ShelfStatus | null; label: string; count: number }[] = [
    { value: null, label: t('shelf.status.all'), count: shelf.total },
    ...STATUS_ORDER.map(status => ({
      value: status,
      label: t(STATUS_KEY[status]),
      count: shelf.counts[status] ?? 0,
    })),
  ]

  return (
    <section>
      <PageHeader
        title={t('shelf.title')}
        // 加载中先不写数量：此刻是 0，写出来是错的，数据到了再补上
        description={!shelf.loading && shelf.total ? t('shelf.description', { count: shelf.total }) : undefined}
      />

      <BookFinder onShelf={onShelfKeys} onAdd={handleAdd} />

      {notice && (
        <p
          role="status"
          className="mb-4 rounded-lg border border-celadon-200 bg-celadon-50 px-4 py-2.5 text-sm text-celadon-700 animate-fade-in"
        >
          {notice}
        </p>
      )}

      {!shelf.loading && shelf.total > 0 && (
        <div className="mb-5 flex flex-wrap gap-1.5">
          {filters.map(item => (
            <Chip
              key={item.value ?? 'all'}
              active={shelf.status === item.value}
              count={item.count}
              onClick={() => shelf.setStatus(item.value)}
            >
              {item.label}
            </Chip>
          ))}
        </div>
      )}

      {shelf.loading ? (
        <Loading />
      ) : shelf.total === 0 ? (
        <Empty title={t('shelf.empty')} hint={t('shelf.emptyHint')} />
      ) : shelf.visible.length > 0 ? (
        <div className="space-y-3">
          {shelf.visible.map((book, index) => (
            <ShelfBookCard
              key={book.id}
              book={book}
              index={index}
              onChangeStatus={shelf.setBookStatus}
              onRemove={shelf.remove}
              onSubmit={shelf.submit}
              onCancelReview={shelf.cancelReview}
            />
          ))}
        </div>
      ) : (
        <Empty title={t('shelf.emptyFilter')} hint={t('shelf.emptyFilterHint')} />
      )}
    </section>
  )
}

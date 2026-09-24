import { Link } from 'react-router-dom'
import type { BookSummary } from '../../api/client'
import { Segmented } from '../../components/ui'
import CategoryTag from '../../components/Category'
import { authorName, bookTitle, useI18n, type MessageKey } from '../../i18n'
import type { ReaderTab } from './useReader'

const TABS: readonly { value: ReaderTab; key: MessageKey }[] = [
  { value: 'notes', key: 'reader.tab.notes' },
  { value: 'source', key: 'reader.tab.source' },
]

/**
 * 书页头：返回、书名、作者与类目，右侧是「笔记 / 原典」页签。
 *
 * 页签只在**这本书确实有原典**时出现（`has_source`）。没有原典还摆一个切过去
 * 就空的页签，是在制造一次必然失望的点击。
 */
export default function BookHeader({
  book,
  tab,
  onTabChange,
}: {
  book: BookSummary
  tab: ReaderTab
  onTabChange: (tab: ReaderTab) => void
}) {
  const { lang, t } = useI18n()

  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3 animate-fade-up">
      <div className="min-w-0">
        <Link
          to="/"
          className="group mb-2 inline-flex items-center gap-1.5 text-sm text-ink-400 transition-colors duration-quick ease-swift hover:text-cinnabar-600"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-3.5 w-3.5 transition-transform duration-quick ease-spring group-hover:-translate-x-0.5"
          >
            <path
              fillRule="evenodd"
              d="M12.7 4.3a1 1 0 010 1.4L8.4 10l4.3 4.3a1 1 0 01-1.4 1.4l-5-5a1 1 0 010-1.4l5-5a1 1 0 011.4 0z"
              clipRule="evenodd"
            />
          </svg>
          {t('reader.back')}
        </Link>
        <h1 className="font-serif text-2xl font-bold tracking-tight text-balance text-ink-900">
          {bookTitle(book.title, lang)}
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-2.5 text-sm text-ink-500">
          <span>{authorName(book.author, lang)}</span>
          <CategoryTag category={book.category} />
        </div>
      </div>

      {book.has_source && (
        <Segmented
          value={tab}
          ariaLabel={t('reader.viewGroup')}
          options={TABS.map(item => ({ value: item.value, label: t(item.key) }))}
          onChange={onTabChange}
        />
      )}
    </div>
  )
}

import { Link } from 'react-router-dom'
import type { BookSummary } from '../../api/client'
import CategoryTag from '../../components/Category'
import { SURFACE } from '../../components/ui'
import { authorName, bookTitle, useI18n } from '../../i18n'

/**
 * 书目卡片。
 *
 * 三个悬停时的微动作，合起来表达"这张卡可以进去"：
 *   · 卡片整体抬 2px、描边转朱砂（来自 `SURFACE.interactive`）
 *   · 左缘一道朱砂竖线自顶端展开——像书脊被抽出来
 *   · 右下角箭头从左侧滑入
 * 全部只碰 transform / opacity / 颜色，不触发布局，所以整屏卡片一起动也不掉帧。
 */
export default function BookCard({ book }: { book: BookSummary }) {
  const { lang, t } = useI18n()

  return (
    <Link
      to={`/books/${book.book_id}`}
      className={`${SURFACE.interactive} group relative flex w-full flex-col overflow-hidden p-5`}
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-4 left-0 w-[3px] origin-top scale-y-0 rounded-full bg-cinnabar-500 transition-transform duration-slow ease-spring group-hover:scale-y-100"
      />

      <div className="mb-3 flex items-start justify-between gap-3">
        <h2 className="font-serif text-lg font-bold leading-snug text-ink-900 transition-colors duration-quick group-hover:text-cinnabar-600">
          {bookTitle(book.title, lang)}
        </h2>
        <CategoryTag category={book.category} />
      </div>

      <p className="text-sm text-ink-500">{authorName(book.author, lang)}</p>

      {/* 这一行是**两段文本直接拼起来的**，中间不能夹任何元素：
          既有契约是 `<p>` 的 textContent 恰好等于「5 章 · 含原典」，
          插一个图标或空格都会让断言失配。右下角的箭头因此放在 `<p>` 外面。 */}
      <div className="mt-auto flex items-center justify-between gap-3 pt-5">
        <p className="text-xs text-ink-400">
          {book.chapter_count > 0
            ? t('library.chapters', { count: book.chapter_count })
            : t('library.noContent')}
          {book.has_source ? t('library.hasSource') : ''}
        </p>
        <svg
          aria-hidden="true"
          viewBox="0 0 16 16"
          fill="none"
          className="h-4 w-4 shrink-0 -translate-x-1 text-cinnabar-500 opacity-0 transition-[opacity,transform] duration-quick ease-spring group-hover:translate-x-0 group-hover:opacity-100"
        >
          <path
            d="M3 8h9m0 0L8.5 4.5M12 8l-3.5 3.5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </Link>
  )
}

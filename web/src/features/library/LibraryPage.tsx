import { Empty, PageHeader } from '../../components/ui'
import { ErrorBox } from '../../components/Status'
import { useI18n } from '../../i18n'
import { BookGrid, BookGridSkeleton } from './BookGrid'
import CategoryBar from './CategoryBar'
import { useLibrary } from './useLibrary'

/** 空书架上的那本书。纯装饰，读屏靠文案。 */
function BookIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
      <path
        d="M4 5.5A1.5 1.5 0 015.5 4H10a2 2 0 012 2v12a1.5 1.5 0 00-1.5-1.5H4V5.5zM20 5.5A1.5 1.5 0 0018.5 4H14a2 2 0 00-2 2v12a1.5 1.5 0 011.5-1.5H20V5.5z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * 书架。
 *
 * 这个文件只负责**编排**：什么时候显示骨架、什么时候显示空态、按什么顺序摆。
 * 数据在 `useLibrary`，卡片在 `BookCard`，网格与骨架在 `BookGrid`，
 * 筛选条在 `CategoryBar`。所以"改筛选规则"和"改版式"是两件互不打扰的事。
 *
 * 三种空态要分清楚，它们的原因完全不同：
 *   · 书目为空      → 这套知识库还没装东西
 *   · 该分类为空    → 筛选太窄了，给一条退回去的路
 *   · 加载失败      → 是错误，不是空，必须能看出来
 * 原来这三者里有两种共用同一句话，用户分不清"没有"和"坏了"。
 */
export default function LibraryPage() {
  const { t } = useI18n()
  const { books, error, loading, category, setCategory, categories, counts, visible } =
    useLibrary()

  if (error) return <ErrorBox message={error} />

  return (
    <section>
      <PageHeader
        title={t('library.title')}
        // 加载中先不写数量：此刻是 0，写出来是错的，数据到了再补上
        description={
          !loading && books.length
            ? t('library.description', { count: books.length })
            : undefined
        }
      />

      {!loading && books.length > 0 && (
        <CategoryBar
          categories={categories}
          counts={counts}
          total={books.length}
          active={category}
          onChange={setCategory}
        />
      )}

      {loading ? (
        <BookGridSkeleton />
      ) : books.length === 0 ? (
        <Empty
          icon={<BookIcon />}
          title={t('library.empty')}
          hint={t('library.emptyHint')}
        />
      ) : visible.length > 0 ? (
        <BookGrid books={visible} />
      ) : (
        <Empty title={t('library.emptyCategory')} hint={t('library.emptyCategoryHint')} />
      )}
    </section>
  )
}

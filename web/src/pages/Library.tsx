import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type BookSummary } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { Loading, ErrorBox, Empty } from '../components/Status'
import CategoryTag from '../components/Category'
import PageHeader from '../components/ui/PageHeader'
import Chip from '../components/ui/Chip'

function BookCard({ book }: { book: BookSummary }) {
  return (
    <Link
      to={`/books/${book.book_id}`}
      className="card group flex flex-col p-5 hover:-translate-y-0.5 hover:border-cinnabar-300 hover:shadow-lift"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <h2 className="font-serif text-lg font-bold leading-snug text-ink-900 transition-colors group-hover:text-cinnabar-600">
          {book.title}
        </h2>
        <CategoryTag category={book.category} />
      </div>
      <p className="text-sm text-ink-500">{book.author}</p>
      <p className="mt-auto pt-5 text-xs text-ink-400">
        {book.chapter_count > 0 ? `${book.chapter_count} 章` : '暂无内容'}
        {book.has_source ? ' · 含原典' : ''}
      </p>
    </Link>
  )
}

export default function Library() {
  const { data: books, error, loading } = useAsync(() => api.listBooks(), [])
  const [category, setCategory] = useState<string | null>(null)

  // 分类顺序按书目顺序首次出现决定，与后端注册表保持一致
  const categories = useMemo(() => {
    const seen: string[] = []
    for (const book of books ?? []) {
      if (!seen.includes(book.category)) seen.push(book.category)
    }
    return seen
  }, [books])

  const visible = useMemo(
    () => (category ? (books ?? []).filter(book => book.category === category) : books ?? []),
    [books, category],
  )

  if (loading) return <Loading />
  if (error) return <ErrorBox message={error} />
  if (!books?.length) return <Empty>书架还是空的</Empty>

  return (
    <section>
      <PageHeader title="书架" description={`${books.length} 部经典 · 点击进入阅读`} />

      <div className="mb-6 flex flex-wrap gap-2">
        <Chip active={category === null} onClick={() => setCategory(null)} count={books.length}>
          全部
        </Chip>
        {categories.map(name => (
          <Chip
            key={name}
            active={category === name}
            onClick={() => setCategory(name)}
            count={books.filter(book => book.category === name).length}
          >
            {name}
          </Chip>
        ))}
      </div>

      {visible.length ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-5 lg:grid-cols-3">
          {visible.map(book => (
            <BookCard key={book.book_id} book={book} />
          ))}
        </div>
      ) : (
        <Empty>该分类下暂无书目</Empty>
      )}
    </section>
  )
}

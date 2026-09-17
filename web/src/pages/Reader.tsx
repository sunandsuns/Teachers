import { useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { useSourceReader } from '../hooks/useSourceReader'
import Markdown from '../components/Markdown'
import CategoryTag from '../components/Category'
import { Loading, ErrorBox, Empty } from '../components/Status'
import Button from '../components/ui/Button'
import Segmented from '../components/ui/Segmented'

type Tab = 'notes' | 'source'

const TABS: { value: Tab; label: string }[] = [
  { value: 'notes', label: '理解笔记' },
  { value: 'source', label: '原典全文' },
]

export default function Reader() {
  const { bookId = '' } = useParams()
  // 支持深链：/books/13?chapter=04 由「寻章」笔记结果跳转而来，
  // /books/13?tab=source&offset=120000 由原典结果跳转而来
  const [searchParams] = useSearchParams()
  const [chapterId, setChapterId] = useState<string | null>(searchParams.get('chapter'))
  const [tab, setTab] = useState<Tab>(searchParams.get('tab') === 'source' ? 'source' : 'notes')
  const sourceOffset = Number(searchParams.get('offset') ?? 0) || 0

  const { data: book, error: bookError, loading: bookLoading } = useAsync(
    () => api.getBook(bookId),
    [bookId],
  )
  const { data: chapters, error: chaptersError } = useAsync(
    () => api.listChapters(bookId),
    [bookId],
  )
  const source = useSourceReader(bookId, tab === 'source', sourceOffset)

  const current = useMemo(
    () => chapters?.find(ch => ch.chapter_id === chapterId) ?? null,
    [chapters, chapterId],
  )
  const { data: chapterDetail } = useAsync(
    () =>
      current ? api.getChapter(bookId, current.chapter_id) : Promise.resolve(null),
    [bookId, current?.chapter_id],
  )

  if (bookLoading) return <Loading />
  if (bookError) return <ErrorBox message={bookError} />
  if (!book) return <Empty>未找到此书</Empty>

  // 只有篇幅超过一块的原典才需要显示翻页进度
  const paginated = source.total > source.chunkSize && source.chunkSize > 0

  return (
    <section>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <Link
            to="/"
            className="mb-2 inline-block text-sm text-ink-400 transition-colors hover:text-cinnabar-600"
          >
            ← 书架
          </Link>
          <h1 className="font-serif text-2xl font-bold tracking-tight text-ink-900">
            {book.title}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-2.5 text-sm text-ink-500">
            <span>{book.author}</span>
            <CategoryTag category={book.category} />
          </div>
        </div>
        {book.has_source && <Segmented value={tab} options={TABS} onChange={setTab} />}
      </div>

      {tab === 'notes' ? (
        <div className="flex flex-col gap-6 lg:flex-row">
          <nav className="lg:w-64 lg:shrink-0" aria-label="章节列表">
            <div className="card overflow-hidden lg:sticky lg:top-20">
              <p className="border-b border-paper-200 px-4 py-2.5 text-xs text-ink-400">
                共 {chapters?.length ?? 0} 章
              </p>
              <ul className="max-h-96 overflow-y-auto p-1.5 lg:max-h-sidebar">
                {chapters?.map(ch => {
                  const selected = chapterId === ch.chapter_id
                  return (
                    <li key={ch.chapter_id}>
                      <button
                        type="button"
                        onClick={() => setChapterId(ch.chapter_id)}
                        aria-current={selected ? 'true' : undefined}
                        className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                          selected
                            ? 'bg-cinnabar-500 font-medium text-paper-50'
                            : 'text-ink-600 hover:bg-paper-200 hover:text-ink-900'
                        }`}
                        title={ch.title}
                      >
                        {ch.title}
                      </button>
                    </li>
                  )
                })}
                {chaptersError && (
                  <li className="px-3 py-2 text-sm text-cinnabar-600">{chaptersError}</li>
                )}
                {!chapters?.length && !chaptersError && (
                  <li className="px-3 py-2 text-sm text-ink-400">暂无章节</li>
                )}
              </ul>
            </div>
          </nav>

          <article className="card min-w-0 flex-1 p-6 sm:p-8">
            {chapterDetail ? (
              <>
                <h2 className="mb-6 border-b border-paper-300 pb-3 font-serif text-xl font-bold text-ink-900">
                  {chapterDetail.title}
                </h2>
                <Markdown content={chapterDetail.content} />
              </>
            ) : (
              <Empty>选择左侧章节开始阅读</Empty>
            )}
          </article>
        </div>
      ) : (
        // 原典正文单独居中成栏：满宽会让一行排到六十余字，中文长文读起来很累
        <article className="card mx-auto w-full max-w-3xl p-6 sm:p-8">
          {source.loading && !source.text && <Loading text="加载原典…" />}
          {source.error && <ErrorBox message={source.error} />}
          {source.text && (
            <>
              {source.startOffset > 0 && (
                <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-paper-300 bg-paper-100 px-4 py-2.5 text-sm text-ink-600">
                  <span>从第 {source.startOffset.toLocaleString()} 字处开始显示</span>
                  <Button variant="secondary" size="sm" onClick={source.restart}>
                    从头读
                  </Button>
                </div>
              )}
              <pre className="whitespace-pre-wrap font-serif text-base leading-loose text-ink-800">
                {source.text}
              </pre>
              {paginated && (
                <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-paper-200 pt-4 text-sm text-ink-500">
                  <span>
                    已载入 {source.startOffset + source.text.length > source.total
                      ? source.total.toLocaleString()
                      : (source.startOffset + source.text.length).toLocaleString()}{' '}
                    / {source.total.toLocaleString()} 字
                  </span>
                  {source.hasMore && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={source.loadMore}
                      disabled={source.loading}
                    >
                      {source.loading ? '载入中…' : '载入后续'}
                    </Button>
                  )}
                </div>
              )}
            </>
          )}
        </article>
      )}
    </section>
  )
}

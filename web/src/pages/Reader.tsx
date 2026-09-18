import { useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { authorName, bookTitle, useI18n, type MessageKey } from '../i18n'
import { useAsync } from '../hooks/useAsync'
import { useSourceReader } from '../hooks/useSourceReader'
import Markdown from '../components/Markdown'
import CategoryTag from '../components/Category'
import { Loading, ErrorBox, Empty } from '../components/Status'
import Button from '../components/ui/Button'
import Segmented from '../components/ui/Segmented'

type Tab = 'notes' | 'source'

const TABS: { value: Tab; key: MessageKey }[] = [
  { value: 'notes', key: 'reader.tab.notes' },
  { value: 'source', key: 'reader.tab.source' },
]

export default function Reader() {
  const { lang, t } = useI18n()
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
  if (!book) return <Empty>{t('reader.notFound')}</Empty>

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
            {t('reader.back')}
          </Link>
          <h1 className="font-serif text-2xl font-bold tracking-tight text-ink-900">
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
            onChange={setTab}
          />
        )}
      </div>

      {tab === 'notes' ? (
        <div className="flex flex-col gap-6 lg:flex-row">
          <nav className="lg:w-64 lg:shrink-0" aria-label={t('reader.chapterList')}>
            <div className="card overflow-hidden lg:sticky lg:top-20">
              <p className="border-b border-paper-200 px-4 py-2.5 text-xs text-ink-400">
                {t('reader.chapterCount', { count: chapters?.length ?? 0 })}
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
                  <li className="px-3 py-2 text-sm text-ink-400">{t('reader.noChapters')}</li>
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
              <Empty>{t('reader.pickChapter')}</Empty>
            )}
          </article>
        </div>
      ) : (
        // 原典正文单独居中成栏：满宽会让一行排到六十余字，中文长文读起来很累
        <article className="card mx-auto w-full max-w-3xl p-6 sm:p-8">
          {source.loading && !source.text && <Loading text={t('reader.loadingSource')} />}
          {source.error && <ErrorBox message={source.error} />}
          {source.text && (
            <>
              {source.startOffset > 0 && (
                <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-paper-300 bg-paper-100 px-4 py-2.5 text-sm text-ink-600">
                  <span>
                    {t('reader.startAt', { offset: source.startOffset.toLocaleString() })}
                  </span>
                  <Button variant="secondary" size="sm" onClick={source.restart}>
                    {t('reader.fromStart')}
                  </Button>
                </div>
              )}
              <pre className="whitespace-pre-wrap font-serif text-base leading-loose text-ink-800">
                {source.text}
              </pre>
              {paginated && (
                <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-paper-200 pt-4 text-sm text-ink-500">
                  <span>
                    {t('reader.progress', {
                      loaded: (source.startOffset + source.text.length > source.total
                        ? source.total
                        : source.startOffset + source.text.length
                      ).toLocaleString(),
                      total: source.total.toLocaleString(),
                    })}
                  </span>
                  {source.hasMore && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={source.loadMore}
                      disabled={source.loading}
                    >
                      {source.loading ? t('reader.loading') : t('reader.loadMore')}
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

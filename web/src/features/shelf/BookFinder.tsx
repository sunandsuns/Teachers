import { useState, type FormEvent } from 'react'
import { api, type BookCandidate } from '../../api/client'
import { Button, Card, Empty } from '../../components/ui'
import Spinner from '../../components/ui/Spinner'
import { useI18n } from '../../i18n'

interface BookFinderProps {
  /** 书架上已有的 source_key。用来把"已经在架上了"的候选标出来 */
  onShelf: ReadonlySet<string>
  /** 加书。抛错由调用方决定怎么显示 */
  onAdd: (candidate: BookCandidate) => Promise<void>
}

/**
 * 「找一本书加进来」。
 *
 * 流程刻意分成两步：**先检索、再由用户挑**。一步到位的做法（输入书名就直接
 * 把第一条塞进书架）看着省事，但同一本书在 OpenLibrary 里可能有十几个版本
 * （不同译者、不同年份、甚至不同作者的重名书），挑错一次用户还得自己去删。
 * 把选择权交回去，多一次点击，少一次返工。
 *
 * 检索是**需要登录**的：加书是写操作，而搜索本身也贴着用户身份（将来要按
 * 用户的书架去重）。未登录时这个组件根本不会渲染——「我的书架」整条路由
 * 都在 `RequireAuth` 那一组里，进不去就轮不到它出场。
 */
export default function BookFinder({ onShelf, onAdd }: BookFinderProps) {
  const { t } = useI18n()
  const [title, setTitle] = useState('')
  const [author, setAuthor] = useState('')
  const [results, setResults] = useState<BookCandidate[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')
  const [addingKey, setAddingKey] = useState('')

  async function onSearch(event: FormEvent) {
    event.preventDefault()
    const trimmed = title.trim()
    if (!trimmed || searching) return
    setSearching(true)
    setError('')
    try {
      const data = await api.searchBooks(trimmed, author.trim())
      setResults(data.results)
      // 上游说"这次没搜成"（限流、词太短）时，`results` 是空的、`error` 有话说。
      // 两者都空才是真的"没有这本书"。
      setError(data.error)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setResults(null)
    } finally {
      setSearching(false)
    }
  }

  async function handleAdd(candidate: BookCandidate) {
    const key = candidate.source_key || candidate.title
    setAddingKey(key)
    setError('')
    try {
      await onAdd(candidate)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setAddingKey('')
    }
  }

  return (
    <Card className="mb-7 p-5">
      <h2 className="mb-1 font-serif text-base font-semibold text-ink-800">
        {t('shelf.findTitle')}
      </h2>
      <p className="mb-4 text-xs text-ink-400">{t('shelf.findHint')}</p>

      <form onSubmit={onSearch} className="flex flex-wrap gap-2">
        <input
          value={title}
          onChange={event => setTitle(event.target.value)}
          placeholder={t('shelf.titlePlaceholder')}
          aria-label={t('shelf.titlePlaceholder')}
          className="min-w-0 flex-1 basis-40 rounded-lg border border-paper-300 bg-paper-50 px-3 py-2 text-sm text-ink-900 outline-none transition-[border-color,box-shadow] duration-quick placeholder:text-ink-300 focus:border-cinnabar-400 focus:ring-2 focus:ring-cinnabar-500/15"
        />
        <input
          value={author}
          onChange={event => setAuthor(event.target.value)}
          placeholder={t('shelf.authorPlaceholder')}
          aria-label={t('shelf.authorPlaceholder')}
          className="min-w-0 flex-1 basis-32 rounded-lg border border-paper-300 bg-paper-50 px-3 py-2 text-sm text-ink-900 outline-none transition-[border-color,box-shadow] duration-quick placeholder:text-ink-300 focus:border-cinnabar-400 focus:ring-2 focus:ring-cinnabar-500/15"
        />
        <Button type="submit" loading={searching} disabled={!title.trim()}>
          {searching ? t('shelf.searching') : t('shelf.searchAction')}
        </Button>
      </form>

      {error && (
        <p role="alert" className="mt-3 text-sm text-cinnabar-600 animate-fade-in">
          {error}
        </p>
      )}

      {searching && !results && (
        <div className="mt-4 flex items-center gap-2 text-sm text-ink-400">
          <Spinner size="sm" />
          {t('shelf.searching')}
        </div>
      )}

      {results !== null && results.length === 0 && !error && (
        <Empty title={t('shelf.noResults')} hint={t('shelf.noResultsHint')} className="py-10" />
      )}

      {results !== null && results.length > 0 && (
        <ul className="mt-4 space-y-2">
          {results.map(candidate => {
            const key = candidate.source_key || candidate.title
            const already = onShelf.has(candidate.source_key) && candidate.source_key !== ''
            return (
              <li
                key={key}
                className="flex items-start gap-3 rounded-lg border border-paper-200 bg-paper-50/60 p-3"
              >
                <Cover candidate={candidate} />
                <div className="min-w-0 flex-1">
                  <p className="font-serif text-sm font-semibold text-ink-900">
                    {candidate.title}
                  </p>
                  <p className="mt-0.5 text-xs text-ink-500">
                    {[candidate.author || t('shelf.unknownAuthor'), candidate.year]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                  {candidate.subjects.length > 0 && (
                    <p className="mt-1 line-clamp-1 text-xs text-ink-400">
                      {candidate.subjects.slice(0, 4).join(' / ')}
                    </p>
                  )}
                </div>
                <Button
                  size="sm"
                  variant={already ? 'secondary' : 'primary'}
                  disabled={already}
                  loading={addingKey === key}
                  onClick={() => handleAdd(candidate)}
                >
                  {already ? t('shelf.added') : addingKey === key ? t('shelf.adding') : t('shelf.add')}
                </Button>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}

/** 候选书的封面。没有封面时留一块同尺寸的灰底，避免每行高度不一样。 */
function Cover({ candidate }: { candidate: BookCandidate }) {
  if (!candidate.cover_url) {
    return (
      <div
        aria-hidden="true"
        className="h-16 w-11 shrink-0 rounded bg-paper-200/70"
      />
    )
  }
  return (
    <img
      src={candidate.cover_url}
      alt=""
      loading="lazy"
      className="h-16 w-11 shrink-0 rounded object-cover shadow-card"
    />
  )
}

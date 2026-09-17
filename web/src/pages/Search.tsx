import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type SearchKind, type SearchResultItem } from '../api/client'
import { Loading, ErrorBox } from '../components/Status'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Chip from '../components/ui/Chip'
import PageHeader from '../components/ui/PageHeader'
import Segmented from '../components/ui/Segmented'

const EXAMPLES = ['自强不息', '知足者富', '不战而屈人之兵', '才者德之资也', '上善若水']

const KIND_TABS: { value: SearchKind; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'notes', label: '深读笔记' },
  { value: 'source', label: '原典全文' },
]

/** 结果深链：笔记跳到具体章节，原典跳到原典页并定位到那一段。 */
function resultLink(result: SearchResultItem): string {
  if (result.kind === 'source') {
    return `/books/${result.book_id}?tab=source&offset=${result.offset}`
  }
  return `/books/${result.book_id}?chapter=${encodeURIComponent(result.chapter_id)}`
}

/**
 * 寻章：跨全库检索——既查深读笔记，也查原典全文。
 *
 * 结果直接深链回 Reader 页：笔记定位到章节，原典定位到字符位置。
 */
export default function Search() {
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState<SearchKind>('all')
  const [results, setResults] = useState<SearchResultItem[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(raw: string, nextKind: SearchKind = kind) {
    const keyword = raw.trim()
    if (!keyword || searching) return
    setSearching(true)
    setError(null)
    try {
      const resp = await api.search(keyword, 12, nextKind)
      setResults(resp.results)
    } catch (err) {
      setError(err instanceof Error ? err.message : '检索失败，请稍后再试')
    } finally {
      setSearching(false)
    }
  }

  function switchKind(next: SearchKind) {
    setKind(next)
    if (query.trim()) void run(query, next)
  }

  return (
    <section>
      <PageHeader
        title="寻章"
        description="在全部经典的深读笔记与原典全文中检索一句话，直接跳到它所在的位置"
      />

      <form
        onSubmit={event => {
          event.preventDefault()
          run(query)
        }}
        className="mb-4 flex flex-col gap-2 sm:flex-row"
      >
        <input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="输入关键词，例如：上善若水"
          aria-label="检索关键词"
          className="field min-w-0 flex-1 font-serif"
        />
        <Button
          type="submit"
          disabled={searching || !query.trim()}
          className="shrink-0 sm:px-6"
        >
          检索
        </Button>
      </form>

      <div className="mb-6">
        <Segmented value={kind} options={KIND_TABS} onChange={switchKind} />
      </div>

      {results === null && (
        <div className="card p-8 text-center">
          <p className="font-serif text-base text-ink-500">试试这些关键词：</p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {EXAMPLES.map(word => (
              <Chip
                key={word}
                onClick={() => {
                  setQuery(word)
                  run(word)
                }}
              >
                {word}
              </Chip>
            ))}
          </div>
        </div>
      )}

      {searching && <Loading text="正在翻检经典…" />}
      {error && <ErrorBox message={error} />}

      {results !== null && !searching && (
        <>
          <p className="mb-4 text-sm text-ink-500">
            {results.length ? `命中 ${results.length} 段` : '没有找到相关段落，换个词试试'}
          </p>
          <ol className="space-y-3">
            {results.map(result => (
              <li key={`${result.book_id}-${result.chapter_id}-${result.offset}-${result.score}`}>
                <Link
                  to={resultLink(result)}
                  className="card block p-5 animate-fade-up hover:border-cinnabar-300 hover:shadow-lift"
                >
                  <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                    <span className="flex items-center gap-2">
                      <Badge tone={result.kind === 'source' ? 'ink' : 'brand'}>
                        {result.kind === 'source' ? '原典' : '笔记'}
                      </Badge>
                      <span className="font-serif text-sm font-bold text-cinnabar-600">
                        {result.source}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-ink-400">
                      相关度 {result.score.toFixed(3)}
                    </span>
                  </div>
                  <p className="line-clamp-4 whitespace-pre-wrap font-serif text-sm leading-relaxed text-ink-700">
                    {result.content}
                  </p>
                </Link>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  )
}

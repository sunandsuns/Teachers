import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type SearchKind, type SearchResultItem } from '../api/client'
import { sourceLabel, useI18n, type MessageKey } from '../i18n'
import { Loading, ErrorBox } from '../components/Status'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Chip from '../components/ui/Chip'
import PageHeader from '../components/ui/PageHeader'
import Segmented from '../components/ui/Segmented'

/** 示例词固定用中文：检索是在中文语料上做的分词匹配，
 * 换成英文关键词只会得到空结果——与其给一个点了没用的示例，
 * 不如保留中文词，并在输入框提示里说明"要输中文"。 */
const EXAMPLES = ['自强不息', '知足者富', '不战而屈人之兵', '才者德之资也', '上善若水']

const KIND_TABS: { value: SearchKind; key: MessageKey }[] = [
  { value: 'all', key: 'search.kind.all' },
  { value: 'notes', key: 'search.kind.notes' },
  { value: 'source', key: 'search.kind.source' },
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
  const { lang, t } = useI18n()
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
      setError(err instanceof Error ? err.message : t('search.failed'))
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
      <PageHeader title={t('search.title')} description={t('search.description')} />

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
          placeholder={t('search.placeholder')}
          aria-label={t('search.keywordLabel')}
          className="field min-w-0 flex-1 font-serif"
        />
        <Button
          type="submit"
          disabled={searching || !query.trim()}
          className="shrink-0 sm:px-6"
        >
          {t('search.submit')}
        </Button>
      </form>

      <div className="mb-6">
        <Segmented
          value={kind}
          ariaLabel={t('search.scopeGroup')}
          options={KIND_TABS.map(tab => ({ value: tab.value, label: t(tab.key) }))}
          onChange={switchKind}
        />
      </div>

      {results === null && (
        <div className="card p-8 text-center">
          <p className="font-serif text-base text-ink-500">{t('search.examplesTitle')}</p>
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

      {searching && <Loading text={t('search.searching')} />}
      {error && <ErrorBox message={error} />}

      {results !== null && !searching && (
        <>
          <p className="mb-4 text-sm text-ink-500">
            {results.length
              ? t('search.hits', { count: results.length })
              : t('search.noHits')}
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
                        {result.kind === 'source'
                          ? t('search.badge.source')
                          : t('search.badge.notes')}
                      </Badge>
                      <span className="font-serif text-sm font-bold text-cinnabar-600">
                        {sourceLabel(result.source, lang)}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-ink-400">
                      {t('search.score', { score: result.score.toFixed(3) })}
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

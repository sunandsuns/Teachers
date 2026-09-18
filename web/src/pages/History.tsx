import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type HistoryItem, type HistoryStatus } from '../api/client'
import Markdown from '../components/Markdown'
import { Empty, ErrorBox, Loading } from '../components/Status'
import Button from '../components/ui/Button'
import PageHeader from '../components/ui/PageHeader'
import { useI18n, type Lang } from '../i18n'
import type { MessageKey } from '../i18n'

/** 一页取多少条。取多了首屏要等，取少了翻页次数多。 */
const PAGE_SIZE = 20

type Translate = (key: MessageKey, params?: Record<string, string | number>) => string

/** 时间戳 → "刚刚 / 3 小时前 / 9月14日 20:31"。
 *
 * 历史记录的价值在"这是什么时候问的"，绝对时间戳对人不友好；
 * 超过一周才退回具体日期，那时"几天前"已经算不清了。 */
function formatTime(ts: number, t: Translate, lang: Lang): string {
  const date = new Date(ts * 1000)
  const elapsed = Date.now() - date.getTime()
  const minute = 60_000
  const hour = 60 * minute
  const day = 24 * hour

  if (elapsed < minute) return t('history.justNow')
  if (elapsed < hour) return t('history.minutesAgo', { count: Math.floor(elapsed / minute) })
  if (elapsed < day) return t('history.hoursAgo', { count: Math.floor(elapsed / hour) })
  if (elapsed < 7 * day) return t('history.daysAgo', { count: Math.floor(elapsed / day) })

  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}`
  if (lang === 'en') {
    // 英文里"Oct 2, 20:31"，月份缩写比"10 月"更自然
    const month = new Intl.DateTimeFormat('en', { month: 'short' }).format(date)
    return `${month} ${date.getDate()}, ${time}`
  }
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日 ${time}`
}

const pad = (value: number) => String(value).padStart(2, '0')

/** ISO 时间 → "9 月 30 日"。用来告诉用户下次什么时候清理。 */
function formatDay(iso: string | null, t: Translate, lang: Lang): string {
  if (!iso) return t('history.noDate')
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return t('history.noDate')
  if (lang === 'en') {
    return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(date)
  }
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日`
}

/** 存储概况那条小字：有多少条、留多久、下次何时清理。 */
function StatusLine({ status }: { status: HistoryStatus }) {
  const { lang, t } = useI18n()
  const dot = (
    <span aria-hidden="true" className="mx-2 text-paper-400">
      ·
    </span>
  )
  return (
    <div className="mb-6 space-y-1">
      <p className="text-sm text-ink-500">
        {t('history.total', { count: status.total })}
        {dot}
        {t('history.retention', { days: Math.round(status.retention_days) })}
        {dot}
        {t('history.nextPurge', { day: formatDay(status.next_purge_at, t, lang) })}
      </p>
      {/* 把库的位置写出来：用户想备份或彻底删掉时，得知道去哪儿找 */}
      <p className="break-all text-xs text-ink-400">
        {t('history.dbPath', { path: status.db_path })}
      </p>
    </div>
  )
}

export default function History() {
  const { lang, t } = useI18n()
  const navigate = useNavigate()
  const [items, setItems] = useState<HistoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [status, setStatus] = useState<HistoryStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [more, setMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 列表与概况一起取：两者都要，分两次发只是多一个来回。
  // 概况这一趟还会让后端顺带做一次过期清理（见 services/history.py）。
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [listing, storage] = await Promise.all([api.listHistory(PAGE_SIZE, 0), api.historyStatus()])
      setItems(listing.items)
      setTotal(listing.total)
      setStatus(storage)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('history.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void load()
  }, [load])

  async function loadMore() {
    setMore(true)
    try {
      const listing = await api.listHistory(PAGE_SIZE, items.length)
      setItems(prev => [...prev, ...listing.items])
      setTotal(listing.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('history.loadMoreFailed'))
    } finally {
      setMore(false)
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteHistory(id)
      setItems(prev => prev.filter(item => item.id !== id))
      setTotal(prev => Math.max(0, prev - 1))
      // 概况里的总数也要跟着动，否则那句"共 N 条"会立刻说谎
      setStatus(prev => (prev ? { ...prev, total: Math.max(0, prev.total - 1) } : prev))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('history.deleteFailed'))
    }
  }

  async function clearAll() {
    // 清空是不可撤销的，问一句再动手
    if (!window.confirm(t('history.confirmClear'))) return
    try {
      await api.clearHistory()
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('history.clearFailed'))
    }
  }

  const unavailable = status !== null && !status.available

  return (
    <section className="mx-auto w-full max-w-3xl">
      <PageHeader title={t('history.title')} description={t('history.description')}>
        {total > 0 && (
          <Button variant="secondary" size="sm" onClick={clearAll}>
            {t('history.clear')}
          </Button>
        )}
      </PageHeader>

      {status && <StatusLine status={status} />}

      {unavailable && (
        <ErrorBox message={t('history.unavailable', { error: status.error })} />
      )}

      {loading && <Loading text={t('history.loading')} />}
      {error && <ErrorBox message={error} />}

      {!loading && !unavailable && items.length === 0 && <Empty>{t('history.empty')}</Empty>}

      <div className="space-y-5">
        {items.map(item => (
          <article key={item.id} className="card p-5 animate-fade-up">
            <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
              <h2 className="min-w-0 font-serif text-base font-bold leading-relaxed text-ink-900">
                {item.question}
              </h2>
              <span className="shrink-0 pt-0.5 text-xs text-ink-400">
                {formatTime(item.created_ts, t, lang)}
              </span>
            </header>

            <div className="mt-3 border-t border-paper-200 pt-3">
              <Markdown content={item.answer} />
            </div>

            <footer className="mt-3 flex flex-wrap items-center gap-2 border-t border-paper-200 pt-3 text-xs text-ink-400">
              <span>{t('history.cited', { count: item.retrieved_count })}</span>
              <span aria-hidden="true" className="h-1 w-1 rounded-full bg-paper-400" />
              <span>
                {item.llm_used
                  ? t('history.aiAnswer', { model: item.model ?? '' })
                  : t('history.localMode')}
              </span>
              <span className="ml-auto flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate(`/ask?q=${encodeURIComponent(item.question)}`)}
                >
                  {t('history.askAgain')}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => remove(item.id)}>
                  {t('history.delete')}
                </Button>
              </span>
            </footer>
          </article>
        ))}
      </div>

      {items.length < total && (
        <div className="flex justify-center pt-6">
          <Button variant="secondary" onClick={loadMore} disabled={more}>
            {more
              ? t('history.loadMoreBusy')
              : t('history.loadMore', { count: total - items.length })}
          </Button>
        </div>
      )}
    </section>
  )
}

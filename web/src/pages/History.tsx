/** 「回响」（求教历史）页面。
 *
 * 列表按**话题**聚合：一次会话里的连续追问算一个话题，列表上是卡片，
 * 点开才展开那段对话。平铺的列表追问几轮就没法看了——同一件事会散成好几条，
 * 每条再贴一遍整篇回答。
 *
 * 两条不变的契约（别的都是排版）：
 *
 * 1. **列表与概况是两件事**——概况来自 `/api/history/status`，它同时负责告诉
 *    用户"记录留多久、下次什么时候清理"。删掉东西之后那句"共 N 条"必须跟着变，
 *    否则界面当场自相矛盾。
 * 2. **数据库不可用不是错误页**——`available: false` 时要照常渲染、说明原因，
 *    而不是弹一个红色报错或者显示成"还没有记录"（那会让人以为记录丢了）。
 */

import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type HistoryItem, type HistoryStatus, type TopicItem } from '../api/client'
import Markdown from '../components/Markdown'
import { Empty, ErrorBox, Loading } from '../components/Status'
import Button from '../components/ui/Button'
import PageHeader from '../components/ui/PageHeader'
import { useI18n, type Lang } from '../i18n'
import type { MessageKey } from '../i18n'

/** 一页取多少个话题。取多了首屏要等，取少了翻页次数多。 */
const PAGE_SIZE = 20

/** 卡片上那段预览的字符上限。 */
const PREVIEW_LIMIT = 120

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

/** 回答是整篇 Markdown，卡片上只摊平取开头一小段。
 *
 * 不用 CSS 的多行截断：Markdown 里换行与标记符号都得先压掉，
 * 否则预览第一行可能只有个 `##`。 */
function preview(text: string): string {
  const flat = text
    .replace(/[#>*`|-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return flat.length > PREVIEW_LIMIT ? `${flat.slice(0, PREVIEW_LIMIT)}…` : flat
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
  const [topics, setTopics] = useState<TopicItem[]>([])
  //: 话题总数（不是记录数——记录总数在 status 里）
  const [topicTotal, setTopicTotal] = useState(0)
  const [status, setStatus] = useState<HistoryStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [more, setMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  //: 展开的是哪个话题
  const [openTopic, setOpenTopic] = useState<string | null>(null)
  //: 取回来的话题记录按话题 id 缓存——反复折叠不该重复请求
  const [records, setRecords] = useState<Record<string, HistoryItem[]>>({})
  const [opening, setOpening] = useState<string | null>(null)

  // 列表与概况一起取：两者都要，分两次发只是多一个来回。
  // 概况这一趟还会让后端顺带做一次过期清理（见 services/history.py）。
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [listing, storage] = await Promise.all([
        api.listTopics(PAGE_SIZE, 0),
        api.historyStatus(),
      ])
      setTopics(listing.items)
      setTopicTotal(listing.total)
      setStatus(storage)
      setRecords({})
      setOpenTopic(null)
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
      const listing = await api.listTopics(PAGE_SIZE, topics.length)
      setTopics(prev => [...prev, ...listing.items])
      setTopicTotal(listing.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('history.loadMoreFailed'))
    } finally {
      setMore(false)
    }
  }

  async function toggleTopic(topic: TopicItem) {
    if (openTopic === topic.id) {
      setOpenTopic(null)
      return
    }
    setOpenTopic(topic.id)
    if (records[topic.id]) return
    setOpening(topic.id)
    try {
      const listing = await api.topicRecords(topic.id)
      setRecords(prev => ({ ...prev, [topic.id]: listing.items }))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('history.loadFailed'))
    } finally {
      setOpening(null)
    }
  }

  async function removeRecord(topicId: string, id: number) {
    try {
      await api.deleteHistory(id)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('history.deleteFailed'))
      return
    }
    const rest = (records[topicId] ?? []).filter(item => item.id !== id)
    setRecords(prev => ({ ...prev, [topicId]: rest }))
    // 概况那行写的是记录总数，删一条就得跟着减
    setStatus(prev => (prev ? { ...prev, total: Math.max(0, prev.total - 1) } : prev))
    if (rest.length === 0) {
      // 话题空了就整张卡片撤掉，别留一个"0 轮追问"在那儿
      setTopics(prev => prev.filter(item => item.id !== topicId))
      setTopicTotal(prev => Math.max(0, prev - 1))
      setOpenTopic(null)
    } else {
      setTopics(prev =>
        prev.map(item =>
          item.id === topicId ? { ...item, question_count: rest.length } : item,
        ),
      )
    }
  }

  async function removeTopic(topic: TopicItem) {
    // 整段删掉是不可撤销的，问一句再动手
    if (!window.confirm(t('history.confirmDeleteTopic', { count: topic.question_count }))) return
    try {
      const result = await api.deleteTopic(topic.id)
      setTopics(prev => prev.filter(item => item.id !== topic.id))
      setTopicTotal(prev => Math.max(0, prev - 1))
      setStatus(prev =>
        prev ? { ...prev, total: Math.max(0, prev.total - result.deleted) } : prev,
      )
      setRecords(prev => {
        const next = { ...prev }
        delete next[topic.id]
        return next
      })
      setOpenTopic(null)
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
        {topicTotal > 0 && (
          <Button variant="secondary" size="sm" onClick={clearAll}>
            {t('history.clear')}
          </Button>
        )}
      </PageHeader>

      {status && <StatusLine status={status} />}

      {unavailable && <ErrorBox message={t('history.unavailable', { error: status.error })} />}

      {loading && <Loading text={t('history.loading')} />}
      {error && <ErrorBox message={error} />}

      {!loading && !unavailable && topics.length === 0 && <Empty>{t('history.empty')}</Empty>}

      <div className="space-y-4">
        {topics.map(topic => {
          const open = openTopic === topic.id
          const items = records[topic.id] ?? []
          return (
            <article key={topic.id} className="card animate-fade-up">
              <button
                type="button"
                onClick={() => void toggleTopic(topic)}
                aria-expanded={open}
                className="w-full px-5 py-4 text-left"
              >
                <span className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
                  <span className="min-w-0 break-words font-serif text-base font-bold leading-relaxed text-ink-900">
                    {topic.title}
                  </span>
                  <span className="shrink-0 pt-0.5 text-xs text-ink-400">
                    {formatTime(topic.last_ts, t, lang)}
                  </span>
                </span>
                {/* 收起时给一段预览：不点开也能想起这件事聊到哪了 */}
                {!open && (
                  <span className="mt-2 block text-sm leading-relaxed text-ink-500">
                    {preview(topic.latest_answer)}
                  </span>
                )}
                <span className="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-400">
                  <span>{t('history.topicTurns', { count: topic.question_count })}</span>
                  <span aria-hidden="true" className="h-1 w-1 rounded-full bg-paper-400" />
                  <span>{open ? t('history.collapse') : t('history.expand')}</span>
                </span>
              </button>

              {open && (
                <div className="mx-5 border-t border-paper-200 pb-5 pt-4">
                  {opening === topic.id && <Loading text={t('history.loadingTopic')} />}

                  <div className="space-y-5">
                    {items.map(record => (
                      <div key={record.id} className="space-y-2">
                        <p className="break-words font-serif text-sm font-bold leading-relaxed text-ink-900">
                          {record.question}
                        </p>
                        <Markdown content={record.answer} />
                        <div className="flex flex-wrap items-center gap-2 border-t border-paper-200 pt-2 text-xs text-ink-400">
                          <span>{formatTime(record.created_ts, t, lang)}</span>
                          <span aria-hidden="true" className="h-1 w-1 rounded-full bg-paper-400" />
                          <span>{t('history.cited', { count: record.retrieved_count })}</span>
                          <span aria-hidden="true" className="h-1 w-1 rounded-full bg-paper-400" />
                          <span>
                            {record.llm_used
                              ? t('history.aiAnswer', { model: record.model ?? '' })
                              : t('history.localMode')}
                          </span>
                          <span className="ml-auto flex items-center gap-1">
                            {/* 带上话题一起跳过去：接着问的问题仍归在这件事下 */}
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                navigate(
                                  `/ask?q=${encodeURIComponent(record.question)}` +
                                    `&topic=${encodeURIComponent(topic.id)}`,
                                )
                              }
                            >
                              {t('history.askAgain')}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => void removeRecord(topic.id, record.id)}
                            >
                              {t('history.delete')}
                            </Button>
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 flex justify-end">
                    <Button variant="ghost" size="sm" onClick={() => void removeTopic(topic)}>
                      {t('history.deleteTopic')}
                    </Button>
                  </div>
                </div>
              )}
            </article>
          )
        })}
      </div>

      {topics.length < topicTotal && (
        <div className="flex justify-center pt-6">
          <Button variant="secondary" onClick={loadMore} disabled={more}>
            {more
              ? t('history.loadMoreBusy')
              : t('history.loadMore', { count: topicTotal - topics.length })}
          </Button>
        </div>
      )}
    </section>
  )
}

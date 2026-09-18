/** 「回响」（求教历史）页面。
 *
 * 列表按**话题**聚合：一次会话里的连续追问算一个话题，列表上是卡片，
 * 点开才展开那段对话。平铺的列表追问几轮就没法看了——同一件事会散成好几条，
 * 每条再贴一遍整篇回答。
 *
 * 四条不变的契约（别的都是排版）：
 *
 * 1. **列表与概况是两件事**——概况来自 `/api/history/status`，它同时负责告诉
 *    用户"记录留多久、下次什么时候清理"。删掉东西之后那句"共 N 条"必须跟着变，
 *    否则界面当场自相矛盾。
 * 2. **数据库不可用不是错误页**——`available: false` 时要照常渲染、说明原因，
 *    而不是弹一个红色报错或者显示成"还没有记录"（那会让人以为记录丢了）。
 * 3. **删除可以挑着来**——除了单条删、整段删、清空，还能进「选择」模式勾一批
 *    **混着删**（几段对话 + 几条单独的问答），一次请求交出去。
 * 4. **整段勾中之后，段内每条不再单独给勾选框**——它们注定一起走，再让人勾一遍
 *    只会徒增怀疑："我是不是漏了哪一条？"。想只删其中一条，就先取消整段的勾选。
 * 5. **问"删不删"一律用页内的确认条，不许用 `window.confirm`**——原生 modal 在
 *    嵌入式页面里会被静默拦掉（返回 false），点下去一点动静都没有。详见
 *    `components/ui/ConfirmBar`。
 */

import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type HistoryItem, type HistoryStatus, type TopicItem } from '../api/client'
import Markdown from '../components/Markdown'
import { Empty, ErrorBox, Loading } from '../components/Status'
import Button from '../components/ui/Button'
import ConfirmBar from '../components/ui/ConfirmBar'
import PageHeader from '../components/ui/PageHeader'
import { useI18n, type Lang } from '../i18n'
import type { MessageKey } from '../i18n'

/** 一页取多少个话题。取多了首屏要等，取少了翻页次数多。 */
const PAGE_SIZE = 20

/** 卡片上那段预览的字符上限。 */
const PREVIEW_LIMIT = 120

type Translate = (key: MessageKey, params?: Record<string, string | number>) => string

/** 要先问一句再动手的删除动作。
 *
 * 刻意只存"要做哪件事"，不存目标清单：真正执行时按**当时**的勾选去算，
 * 免得在确认条上停留的那几秒里，数据已经和弹出来时不是一回事了。
 */
type PendingAction =
  | { kind: 'selected' }
  | { kind: 'topic'; topic: TopicItem }
  | { kind: 'all' }

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
  //: 一句轻提示（"已删除 N 条记录"）。与 error 分开：那不是错误，
  //: 不该染成红色吓人一跳
  const [note, setNote] = useState<string | null>(null)
  //: 展开的是哪个话题
  const [openTopic, setOpenTopic] = useState<string | null>(null)
  //: 取回来的话题记录按话题 id 缓存——反复折叠不该重复请求
  const [records, setRecords] = useState<Record<string, HistoryItem[]>>({})
  const [opening, setOpening] = useState<string | null>(null)
  //: 选择模式。开着时卡片上才出现勾选框，工具栏也换成勾选那一套
  const [selecting, setSelecting] = useState(false)
  //: 勾中的话题（整段删）与勾中的单条记录。两个集合分开存，因为删法不同
  const [pickedTopics, setPickedTopics] = useState<ReadonlySet<string>>(new Set())
  const [pickedRecords, setPickedRecords] = useState<ReadonlySet<number>>(new Set())
  //: 删除请求在飞。按钮要禁掉，免得手快连点两次
  const [busy, setBusy] = useState(false)
  //: 待确认的删除动作；非空时页面上会出现一条确认条
  const [pending, setPending] = useState<PendingAction | null>(null)

  /** 清掉全部勾选，并退出选择模式。
   *
   * 重新读取之后一定要调：话题与记录的 id 都可能变了，留着旧勾选，界面上会
   * 出现"勾着一个已经不存在的东西"。
   */
  const dropSelection = useCallback(() => {
    setSelecting(false)
    setPickedTopics(new Set())
    setPickedRecords(new Set())
  }, [])

  // 列表与概况一起取：两者都要，分两次发只是多一个来回。
  // 概况这一趟还会让后端顺带做一次过期清理（见 services/history.py）。
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setNote(null)
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
      // 重新读取之后话题与记录的 id 都可能变了，旧的勾选留着只会指向不存在的东西
      dropSelection()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('history.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t, dropSelection])

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
    // 整段删掉是不可撤销的，先问一句——交给页内的确认条去问
    setPending({ kind: 'topic', topic })
  }

  async function doRemoveTopic(topic: TopicItem) {
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
    // 清空是不可撤销的，先问一句
    setPending({ kind: 'all' })
  }

  async function doClearAll() {
    try {
      await api.clearHistory()
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('history.clearFailed'))
    }
  }

  // ── 勾选删除 ──────────────────────────────────────────────────────────

  /** 勾中 / 取消一整段对话。 */
  function pickTopic(topicId: string) {
    const already = pickedTopics.has(topicId)
    setPickedTopics(prev => {
      const next = new Set(prev)
      if (already) next.delete(topicId)
      else next.add(topicId)
      return next
    })
    // 整段都要走，段内那些单独的勾就多余了——留着还会把总数算重
    if (!already) {
      const inside = new Set((records[topicId] ?? []).map(item => item.id))
      setPickedRecords(prev => {
        const next = new Set(prev)
        inside.forEach(id => next.delete(id))
        return next
      })
    }
  }

  /** 勾中 / 取消一条单独的问答。 */
  function pickRecord(id: number) {
    setPickedRecords(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  /** 全选当前列出的所有话题；已经全选中就反过来全部取消。 */
  function toggleSelectAll() {
    if (pickedTopics.size >= topics.length && topics.length > 0) {
      setPickedTopics(new Set())
    } else {
      setPickedTopics(new Set(topics.map(topic => topic.id)))
      setPickedRecords(new Set())
    }
  }

  /** 勾选删除：先把确认条摆出来，真正动手在 confirmPending 里。 */
  function removeSelected() {
    if (pickedTopics.size + pickedRecords.size === 0) {
      // 一个都没勾就点，也得给句话：静默地什么都不发生，最容易被当成"按钮坏了"
      setNote(t('history.nothingPicked'))
      return
    }
    setPending({ kind: 'selected' })
  }

  async function doRemoveSelected() {
    try {
      const result = await api.deleteSelected({
        topics: [...pickedTopics],
        ids: [...pickedRecords],
      })
      dropSelection()
      // 话题聚合、轮数、总数都变了。在本地逐个推算容易和服务端对不上，
      // 直接重新读一遍最省心（负载很小，一次请求就够）。
      // 注意 setNote 要排在 load 之后：load 开头会把上一条提示清掉。
      await load()
      setNote(t('history.deletedSelected', { count: result.deleted }))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('history.deleteFailed'))
    }
  }

  /** 确认条上按了「确认删除」：这才真正动手。 */
  async function confirmPending() {
    const action = pending
    if (!action) return
    setBusy(true)
    try {
      if (action.kind === 'selected') await doRemoveSelected()
      else if (action.kind === 'topic') await doRemoveTopic(action.topic)
      else await doClearAll()
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  /** 确认条上那句话。数量在这里现算——pending 里只存"要删什么"。 */
  function describePending(action: PendingAction): string {
    if (action.kind === 'selected') {
      return t('history.confirmDeleteSelected', {
        count: pickedTopics.size + pickedRecords.size,
      })
    }
    if (action.kind === 'topic') {
      return t('history.confirmDeleteTopic', { count: action.topic.question_count })
    }
    return t('history.confirmClear')
  }

  const unavailable = status !== null && !status.available
  const pickedCount = pickedTopics.size + pickedRecords.size
  const allPicked = topics.length > 0 && pickedTopics.size >= topics.length

  return (
    <section className="mx-auto w-full max-w-3xl">
      <PageHeader title={t('history.title')} description={t('history.description')}>
        {topicTotal > 0 && (
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => (selecting ? dropSelection() : setSelecting(true))}
              disabled={busy || pending !== null}
            >
              {selecting ? t('history.exitSelect') : t('history.select')}
            </Button>
            {/* 选择模式下把「清空」收起来：清空是"全都要删"，
                与"挑几条删"是两种相反的心智，并排摆着容易点错 */}
            {!selecting && (
              <Button
                variant="secondary"
                size="sm"
                onClick={clearAll}
                disabled={busy || pending !== null}
              >
                {t('history.clear')}
              </Button>
            )}
          </>
        )}
      </PageHeader>

      {/* 确认条摆在最上面，并把选择栏顶掉——两处都报数只会互相打架。
          卡片上的勾选框留着：确认条上的数字是渲染时现算的，改勾选它立刻跟着变，
          用户点头时看到的数就是真会删掉的数 */}
      {pending && (
        <ConfirmBar
          message={describePending(pending)}
          confirmLabel={t('common.confirmDelete')}
          busyLabel={t('common.deleting')}
          cancelLabel={t('common.cancel')}
          busy={busy}
          onConfirm={() => void confirmPending()}
          onCancel={() => setPending(null)}
        />
      )}

      {selecting && !pending && (
        <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-sm bg-paper-50 px-4 py-2.5 ring-1 ring-paper-300">
          <span className="text-sm text-ink-600">
            {pickedCount > 0
              ? t('history.pickedCount', {
                  topics: pickedTopics.size,
                  records: pickedRecords.size,
                })
              : t('history.pickedNone')}
          </span>
          <span className="ml-auto flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={toggleSelectAll} disabled={busy}>
              {allPicked ? t('history.selectNone') : t('history.selectAll')}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void removeSelected()}
              disabled={busy}
              /* 没勾中也让点：点下去会得到一句"还没勾选要删的内容"。
                 灰着按钮虽然"正确"，但用户只会觉得按钮坏了 */
            >
              {t('history.deleteSelected')}
            </Button>
          </span>
        </div>
      )}

      {status && <StatusLine status={status} />}

      {unavailable && <ErrorBox message={t('history.unavailable', { error: status.error })} />}

      {loading && <Loading text={t('history.loading')} />}
      {error && <ErrorBox message={error} />}
      {/* 删除结果用轻提示，不弹红框：删干净了是好事，不是故障 */}
      {note && <p className="mb-4 text-sm text-ink-500">{note}</p>}

      {!loading && !unavailable && topics.length === 0 && <Empty>{t('history.empty')}</Empty>}

      <div className="space-y-4">
        {topics.map(topic => {
          const open = openTopic === topic.id
          const items = records[topic.id] ?? []
          //: 整段已被勾中时，段内每条不再单独给勾选框（它们必然一起走）
          const topicPicked = pickedTopics.has(topic.id)
          return (
            <article key={topic.id} className="card animate-fade-up">
              {/* 勾选框必须在标题按钮**外面**：input 不能嵌在 button 里 */}
              <div className="flex items-start">
                {selecting && (
                  <label className="shrink-0 cursor-pointer pl-5 pt-5 pr-1">
                    <input
                      type="checkbox"
                      className="block h-4 w-4 cursor-pointer accent-cinnabar-600"
                      checked={topicPicked}
                      onChange={() => pickTopic(topic.id)}
                      aria-label={t('history.pickTopic', { title: topic.title })}
                    />
                  </label>
                )}
                <button
                  type="button"
                  onClick={() => void toggleTopic(topic)}
                  aria-expanded={open}
                  className="min-w-0 flex-1 px-5 py-4 text-left"
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
              </div>

              {open && (
                <div className="mx-5 border-t border-paper-200 pb-5 pt-4">
                  {opening === topic.id && <Loading text={t('history.loadingTopic')} />}

                  <div className="space-y-5">
                    {items.map(record => (
                      <div key={record.id} className="flex items-start gap-2">
                        {/* 整段已勾中就整段一起走，这里不再给单个勾选框——
                            否则用户会以为"不勾就不删"，白纠结一场 */}
                        {selecting && !topicPicked && (
                          <label className="shrink-0 cursor-pointer pt-1">
                            <input
                              type="checkbox"
                              className="block h-4 w-4 cursor-pointer accent-cinnabar-600"
                              checked={pickedRecords.has(record.id)}
                              onChange={() => pickRecord(record.id)}
                              aria-label={t('history.pickRecord', {
                                question: record.question,
                              })}
                            />
                          </label>
                        )}
                        <div className="min-w-0 flex-1 space-y-2">
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

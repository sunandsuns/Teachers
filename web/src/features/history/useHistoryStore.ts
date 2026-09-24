import { useCallback, useEffect, useState } from 'react'
import { api, type HistoryItem, type HistoryStatus, type TopicItem } from '../../api/client'
import { useI18n } from '../../i18n'

/** 一页取多少个话题。取多了首屏要等，取少了翻页次数多。 */
export const PAGE_SIZE = 20

/**
 * 「回响」的全部服务端状态与写操作。**这是这一块里唯一碰 `api.*` 的地方。**
 *
 * 页面只拿结果去渲染，所以"列表长什么样"和"数据怎么来、删完怎么同步"
 * 是两个可以分别改的东西。
 *
 * 四条不变量写在这里，因为它们都是**数据一致性**的事，不是排版的事：
 *
 * 1. **列表与概况一起取**——两者都要，分两次发只是多一个来回；
 *    概况这一趟还会让后端顺带做一次过期清理（见 `services/history.py`）。
 * 2. **删一条要同时减三处**——段内条数、概况总数、以及"段空了就撤掉整张卡"。
 *    只改一处，界面当场自相矛盾。
 * 3. **勾选删除后一律重读**——话题聚合、轮数、总数都变了，本地逐个推算容易和
 *    服务端对不上，一次请求最省心。
 * 4. **`available: false` 不是错误**——照常渲染、说明原因，而不是当成空列表
 *    （那会让人以为记录丢了）。
 *
 * `generation` 是给选择层用的：每次数据被**整体替换**就 +1，
 * 选择状态据此复位——话题与记录的 id 都可能变了，留着旧勾选会指向不存在的东西。
 * 用计数器而不是回调，是为了避免"选择层要 topics、数据层要 dropSelection"的循环依赖。
 */
export function useHistoryStore() {
  const { t } = useI18n()

  const [topics, setTopics] = useState<TopicItem[]>([])
  //: 话题总数（不是记录数——记录总数在 status 里）
  const [topicTotal, setTopicTotal] = useState(0)
  const [status, setStatus] = useState<HistoryStatus | null>(null)
  //: 取回来的话题记录按话题 id 缓存——反复折叠不该重复请求
  const [records, setRecords] = useState<Record<string, HistoryItem[]>>({})
  //: 展开的是哪个话题
  const [openTopic, setOpenTopic] = useState<string | null>(null)
  const [opening, setOpening] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [more, setMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  //: 一句轻提示（"已删除 N 条记录"）。与 error 分开：那不是错误，
  //: 不该染成红色吓人一跳
  const [note, setNote] = useState<string | null>(null)
  const [generation, setGeneration] = useState(0)

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
      // 数据整体换过了，让选择层把旧勾选丢掉
      setGeneration(value => value + 1)
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

  /** 展开 / 收起一段对话。记录只在第一次展开时取，之后走缓存。 */
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

  /** 删一条问答。删完段空了就整张卡片撤掉——别留一个"0 轮追问"在那儿。 */
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

  /** 删掉整段对话。调用方负责先确认。 */
  async function deleteTopic(topic: TopicItem) {
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

  /** 清空全部。调用方负责先确认。 */
  async function clearAll() {
    try {
      await api.clearHistory()
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('history.clearFailed'))
    }
  }

  /** 一次请求删掉混选（几段对话 + 几条单独的问答）。
   *
   * 返回服务端报告的删除条数；失败返回 null（原因已写进 error）。
   * 调用方拿这个数去写提示——**不自己猜**，因为话题聚合后条数不好本地推算。 */
  async function deleteSelected(
    topicIds: readonly string[],
    recordIds: readonly number[],
  ): Promise<number | null> {
    try {
      const result = await api.deleteSelected({ topics: [...topicIds], ids: [...recordIds] })
      // 话题聚合、轮数、总数都变了。本地逐个推算容易和服务端对不上，
      // 直接重新读一遍最省心（负载很小，一次请求就够）。
      await load()
      return result.deleted
    } catch (err) {
      setError(err instanceof Error ? err.message : t('history.deleteFailed'))
      return null
    }
  }

  return {
    topics,
    topicTotal,
    status,
    records,
    openTopic,
    opening,
    loading,
    more,
    error,
    note,
    generation,
    setNote,
    load,
    loadMore,
    toggleTopic,
    removeRecord,
    deleteTopic,
    clearAll,
    deleteSelected,
  }
}

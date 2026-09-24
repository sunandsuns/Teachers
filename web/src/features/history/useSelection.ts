import { useEffect, useRef, useState } from 'react'
import type { HistoryItem, TopicItem } from '../../api/client'

/**
 * 勾选状态。**纯客户端状态**，不碰网络——它只回答"哪些被勾了"。
 *
 * 与数据层分开的两个理由：
 *
 * 1. 它们变化的时机不同。数据是"读回来的"，勾选是"点出来的"；
 *    混在一起的话，每次删一条记录都要重新想一遍"勾选该不该清"。
 * 2. 复位规则只有一条，写在**一个地方**（见下面的 effect）比散在四处删改逻辑里可靠。
 *
 * 复位用 `generation` 计数器而不是回调：数据层不必知道选择层的存在，
 * 也就不存在"数据层要 dropSelection、选择层要 topics"的循环依赖。
 *
 * 一条容易漏的规则：**整段勾中之后，段内每条的勾要撤掉**。
 * 它们注定一起走，留着不但把总数算重，还会让人怀疑"我是不是漏了哪一条"。
 */
export function useSelection(
  generation: number,
  topics: readonly TopicItem[],
  records: Record<string, HistoryItem[]>,
) {
  //: 选择模式。开着时卡片上才出现勾选框，工具栏也换成勾选那一套
  const [selecting, setSelecting] = useState(false)
  //: 勾中的话题（整段删）与勾中的单条记录。两个集合分开存，因为删法不同
  const [pickedTopics, setPickedTopics] = useState<ReadonlySet<string>>(() => new Set())
  const [pickedRecords, setPickedRecords] = useState<ReadonlySet<number>>(() => new Set())

  const seenGeneration = useRef(generation)
  useEffect(() => {
    if (seenGeneration.current === generation) return
    seenGeneration.current = generation
    setSelecting(false)
    setPickedTopics(new Set())
    setPickedRecords(new Set())
  }, [generation])

  /** 清掉全部勾选，并退出选择模式。 */
  function dropSelection() {
    setSelecting(false)
    setPickedTopics(new Set())
    setPickedRecords(new Set())
  }

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
    if (topics.length > 0 && pickedTopics.size >= topics.length) {
      setPickedTopics(new Set())
    } else {
      setPickedTopics(new Set(topics.map(topic => topic.id)))
      setPickedRecords(new Set())
    }
  }

  return {
    selecting,
    setSelecting,
    dropSelection,
    pickedTopics,
    pickedRecords,
    pickTopic,
    pickRecord,
    toggleSelectAll,
    pickedCount: pickedTopics.size + pickedRecords.size,
    allPicked: topics.length > 0 && pickedTopics.size >= topics.length,
  }
}

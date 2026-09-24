import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type Avatar, type ProfileResponse, type TraitItem } from '../../api/client'
import { useI18n } from '../../i18n'
import { NO_FIGURE, describeExtract, describeFigure, type CategoryGroup, type Columns } from './constants'

/**
 * 画像的取数与全部写操作。**这一块里唯一碰 `api.*` 的地方。**
 *
 * 三条契约（都是行为，不是排版）：
 *
 * 1. **归纳是异步的，不能挡住首屏。** 一次归纳要走一趟模型，几十秒起步。所以
 *    进页面先渲染已有画像，发现"还有没归纳过的新提问"再在后台补一次。
 * 2. **没有特征不等于出错。** 还没有提问、模型不可用、模型这次没读出东西，
 *    都是正常状态，各自说明原因，不弹红色报错。
 * 3. **两次模型调用必须串起来。** 归纳在前、评人在后，排在同一个 effect 里，
 *    一件没做完就不开始下一件——并行发出去不只是让上游吃两份负载，更糟的是
 *    会拿**旧画像**去评人。
 *
 * 两个 `auto*Ran` ref 是"只做一次"的闸门。少了它，归纳完重新读取画像会再次
 * 满足触发条件，变成自己转圈的死循环。
 */
export function useProfile() {
  const { lang, t } = useI18n()

  const [data, setData] = useState<ProfileResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  /** 待确认的「清空画像」。用页内确认条而不是 window.confirm：
   *  原生弹窗在嵌入式页面里会被静默拦掉，点下去毫无反应。 */
  const [confirmingClear, setConfirmingClear] = useState(false)
  /** 工具栏下面那行状态话：正在归纳 / 这次新增了几条 / 正在评定 */
  const [note, setNote] = useState<string | null>(null)
  /** 后台自动动作每进页面只做一次，否则做完重新读取会再触发一轮。两条各记一个。 */
  const autoExtractRan = useRef(false)
  const autoFigureRan = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.getProfile())
    } catch (err) {
      setError(err instanceof Error ? err.message : t('profile.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void load()
  }, [load])

  const runExtract = useCallback(
    async (pendingCount?: number) => {
      setBusy(true)
      setNote(
        pendingCount ? t('profile.autoExtracting', { count: pendingCount }) : t('profile.extracting'),
      )
      try {
        const result = await api.extractProfile(lang)
        setNote(describeExtract(result, t))
        // 画像变了，选出那个人所依据的东西也就变了——松手让下面的 effect
        // 用新画像重评一次（当周画像没变时它本来就不会动，不必在这儿判断）
        autoFigureRan.current = false
        // 重新读一次：特征、待归纳数都变了，以服务端为准
        setData(await api.getProfile())
      } catch (err) {
        setNote(null)
        setError(err instanceof Error ? err.message : t('profile.extractFailed'))
      } finally {
        setBusy(false)
      }
    },
    [lang, t],
  )

  /** 让模型重评一次"最像你的一位历史人物"。
   *
   *  与归纳共用 `busy` 与那行状态话：两者都是"在等模型"，排在一起反而更清楚，
   *  而且它们本来就被串行调度（见下面的 effect），不会同时出现两个转圈。 */
  const runFigure = useCallback(async () => {
    setBusy(true)
    setNote(t('profile.figure.evaluating'))
    try {
      const result = await api.evaluateFigure(lang)
      setNote(describeFigure(result, t))
      // 只有评出来了才值得重读：别的情况下库里什么都没变
      if (result.ok) setData(await api.getProfile())
    } catch (err) {
      setNote(null)
      setError(err instanceof Error ? err.message : t('profile.figureFailed'))
    } finally {
      setBusy(false)
    }
  }, [lang, t])

  // 进页面时若发现"问过话但还没归纳过"，顺手在后台补一次；补完了再看要不要
  // 评定历史人物。**两件事排在同一个 effect 里，一件没做完就不开始下一件**。
  // 不等它们：页面照常渲染已有的画像与人物。
  useEffect(() => {
    if (loading || !data || !data.available) return
    if (data.pending > 0 && !autoExtractRan.current) {
      autoExtractRan.current = true
      void runExtract(data.pending)
      return
    }
    if (data.figure.needs_refresh && !autoFigureRan.current) {
      autoFigureRan.current = true
      void runFigure()
    }
  }, [loading, data, runExtract, runFigure])

  /** 按分类聚好，并**按后端给的分类顺序**排列——每次打开看到的次序都一样。 */
  const grouped = useMemo<CategoryGroup[]>(() => {
    const byCategory = new Map<string, TraitItem[]>()
    for (const trait of data?.traits ?? []) {
      const list = byCategory.get(trait.category)
      if (list) list.push(trait)
      else byCategory.set(trait.category, [trait])
    }
    return (data?.categories ?? [])
      .filter(category => byCategory.has(category))
      .map(category => ({ category, traits: byCategory.get(category) as TraitItem[] }))
  }, [data])

  // 前半边在左、后半边在右：顺着读下来就是分类清单本身的顺序，
  // 比左右交替更不乱
  const columns = useMemo<Columns>(() => {
    const half = Math.ceil(grouped.length / 2)
    return { left: grouped.slice(0, half), right: grouped.slice(half) }
  }, [grouped])

  async function pickAvatar(next: Avatar) {
    if (!data || data.avatar === next) return
    const previous = data.avatar
    // 先切过去，点了就有反应；存不上再退回来
    setData({ ...data, avatar: next })
    try {
      await api.setAvatar(next)
      // 换册页就是换名录：对面那一册评过谁、有几位候选，只有服务端知道。
      // 只把开关拨过去的话，中间挂着的还是上一册的人。
      autoFigureRan.current = false
      setData(await api.getProfile())
    } catch (err) {
      setData(current => (current ? { ...current, avatar: previous } : current))
      setError(err instanceof Error ? err.message : t('profile.loadFailed'))
    }
  }

  async function removeTrait(trait: TraitItem) {
    try {
      await api.deleteTrait(trait.id)
      setData(current =>
        current
          ? {
              ...current,
              traits: current.traits.filter(item => item.id !== trait.id),
              total: Math.max(0, current.total - 1),
            }
          : current,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : t('profile.deleteFailed'))
    }
  }

  async function doClearAll() {
    try {
      await api.clearProfile()
      setNote(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('profile.deleteFailed'))
    } finally {
      setConfirmingClear(false)
    }
  }

  const unavailable = data !== null && !data.available
  const avatar = data?.avatar ?? 'male'
  const figure = data?.figure ?? NO_FIGURE
  /** 评出来了才换人；名录里查不到（用户改了名录）也退回册页，不留一个空画框。 */
  const chosen = figure.id ? figure : null

  return {
    data,
    loading,
    error,
    busy,
    note,
    confirmingClear,
    unavailable,
    avatar,
    figure,
    chosen,
    grouped,
    columns,
    runExtract,
    runFigure,
    pickAvatar,
    removeTrait,
    /** 打开确认条 */
    askClear: () => setConfirmingClear(true),
    doClearAll,
    cancelClear: () => setConfirmingClear(false),
  }
}

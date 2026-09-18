/** 「画像」页面：从你自己问过的话里，慢慢拼出的"你是谁"。
 *
 * 三条不变的契约（别的都是排版）：
 *
 * 1. **归纳是异步的，不能挡住首屏**。一次归纳要走一趟模型，几十秒起步。所以
 *    进页面先渲染已有画像，发现"还有没归纳过的新提问"再在后台补一次——
 *    让用户对着空白页面等半分钟，比给他一份旧画像还难受。
 * 2. **没有特征不等于出错**。还没有提问、模型不可用、模型这次没读出东西，
 *    都是正常状态，各自说明原因即可，不要弹红色报错——用户会以为功能坏了。
 * 3. **两次模型调用必须串起来**：归纳在前、评定人物在后。同时发出去既让上游
 *    吃两份负载，也是在拿**旧画像**去评人——新归纳出来的特征还没进库。
 *
 * 关于形象与牵引线
 * --------------------------------------------------------------------------
 * 默认的形象是**真实的古画**：明·陈洪绶《仿古图册》里的两页——陶渊明像配男式，
 * 仕女图配女式。同一个册子、同一种绢底、同一路笔法，两式放在一起才像一对。
 * 出处是克利夫兰艺术博物馆的开放数据（CC0）。图片存 `src/assets/`，**只裁到画心**
 * （四边的装裱一律不进图，否则会留一条浅色亮边）；两幅画心比例不同，差额交给
 * 容器的 `object-contain` + `paper-200` 底色去补，看着就是装裱。
 *
 * 画框里也可以换成**一位历史人物**——后端从名录里评出"最像你的那一位"，
 * 理由写在画框下面的题跋里。那两页册页仍留着，是评出人来之前的默认形象：
 * 空着比放一个陌生人好。**男女开关同时是筛选池**，男册只在男性名录里挑人。
 *
 * 两侧是分类卡片，每条牵引线从画心牵到对应的分类上。线的坐标要在**渲染之后**
 * 量出来（getBoundingClientRect），所以走 useLayoutEffect + ResizeObserver。
 * 窄屏下三栏会折成一栏，那时画出来的线是横穿文字的噪线，因此只在够宽时画。
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type Ref,
} from 'react'
import {
  api,
  type Avatar,
  type ExtractResult,
  type FigureInfo,
  type FigureResult,
  type ProfileResponse,
  type TraitItem,
} from '../api/client'
import { Empty, ErrorBox, Loading } from '../components/Status'
import Button from '../components/ui/Button'
import PageHeader from '../components/ui/PageHeader'
import Segmented from '../components/ui/Segmented'
import { useI18n, traitCategory, type MessageKey } from '../i18n'
import figureFemale from '../assets/figure-female.webp'
import figureMale from '../assets/figure-male.webp'

/** 够宽才画牵引线：再窄一点三栏就折成一栏了。 */
const LINES_MIN_WIDTH = 760
/** 牵引线出发的高度范围（占画心高度的比例）。上不过肩、下不过衣摆。 */
const ANCHOR_TOP = 0.22
const ANCHOR_BOTTOM = 0.88
/** 出发点从画心边缘再往里收一点，免得圆点压在画框的边上。 */
const FIGURE_INSET = 0.02

/** 归纳失败时后端给的代号 → 人话。不在表里的（上游错误原文）直接显示。 */
const EXTRACT_CODE_KEYS: Record<string, MessageKey> = {
  no_records: 'profile.err.noRecords',
  llm_disabled: 'profile.err.noLlm',
  nothing_usable: 'profile.err.nothingNew',
}

/** 评定历史人物失败时后端给的代号 → 人话。同样，表外的原文直接显示。 */
const FIGURE_CODE_KEYS: Record<string, MessageKey> = {
  no_traits: 'profile.err.noTraits',
  no_pool: 'profile.err.noPool',
  not_in_pool: 'profile.err.notInPool',
  llm_disabled: 'profile.err.noLlmFigure',
  history_unavailable: 'profile.err.noStore',
}

/** 「最像你的一位历史人物」的空档：还没评过、名录为空、库不可用都长这样。 */
const NO_FIGURE: FigureInfo = {
  id: '',
  name: '',
  era: '',
  blurb: '',
  reason: '',
  credit: '',
  portrait: '',
  week: '',
  chosen_at: '',
  pool_size: 0,
  needs_refresh: false,
}

type Translate = (key: MessageKey, params?: Record<string, string | number>) => string
type Side = 'left' | 'right'

/** 一条牵引线。坐标都已换算成相对舞台的像素。 */
interface LeadLine {
  key: string
  d: string
  fromX: number
  fromY: number
  toX: number
  toY: number
}

/** 一个分类下挂着的全部特征。 */
interface CategoryGroup {
  category: string
  traits: TraitItem[]
}

/** 一次归纳的结果 → 一句给人看的话。 */
function describeExtract(result: ExtractResult, t: Translate): string {
  if (result.extracted > 0) return t('profile.extracted', { count: result.extracted })
  const key = EXTRACT_CODE_KEYS[result.error]
  if (key) return t(key)
  // 上游的原始错误（比如 "HTTP 503：…"）比我们的兜底话更有用
  return result.error || t('profile.nothingNew')
}

/** 一次评定的结果 → 一句给人看的话。选出来了不必报名字，
 *  画框里的题签已经写着是谁。 */
function describeFigure(result: FigureResult, t: Translate): string {
  if (result.ok) return t('profile.figure.done')
  const key = FIGURE_CODE_KEYS[result.error]
  if (key) return t(key)
  return result.error || t('profile.figureFailed')
}

/**
 * 默认形象：两页册页的画心。
 *
 * 两幅画心比例本就不同（陶渊明像略横、仕女图偏竖），所以容器用 `object-contain`：
 * 差额由 `paper-200` 的底色补上，正好当装裱，不必把画硬裁成一个比例。
 *
 * `credit` 是题签式的出处说明。古画不是"素材"，署名与藏地要跟着走——
 * 一是尊重，二是它本身也好看。
 */
const FIGURES: Record<Avatar, { src: string; w: number; h: number; credit: MessageKey }> = {
  male: { src: figureMale, w: 624, h: 607, credit: 'profile.figureCredit.male' },
  female: { src: figureFemale, w: 624, h: 679, credit: 'profile.figureCredit.female' },
}

/**
 * 形象：一页册页，或一位历史人物。
 *
 * 两页册页的差别落在**画本身**——陶渊明是执杖的士人，仕女是低眉回身的女子——
 * 不靠颜色或符号去区分，那样会把"这是谁"变成"这是个什么标签"。
 *
 * ``boxRef`` 只挂在**画框那一层**上（不含题签）：牵引线是量它的边框来定位的，
 * 所以换谁进来都不能改画框的尺寸与位置。
 */
function Figure({
  avatar,
  chosen,
  boxRef,
}: {
  avatar: Avatar
  /** 评出来的那一位；还没评出来时是 null，退回册页 */
  chosen: FigureInfo | null
  boxRef: Ref<HTMLDivElement>
}) {
  const { t } = useI18n()
  const leaf = FIGURES[avatar]
  // 时代与一句话凑成题签的第二行；两样都可能缺，缺了就不留一个孤零零的分隔点
  const subtitle = chosen ? [chosen.era, chosen.blurb].filter(Boolean).join(' · ') : ''

  return (
    <figure className="w-full">
      <div
        ref={boxRef}
        className="aspect-portrait w-full overflow-hidden rounded-sm bg-paper-200 shadow-leaf ring-1 ring-paper-300"
      >
        {/* 册页两幅画心的尺寸是写死的，用来提示固有比例；名录里的人尺寸各异，
            交给 `object-contain` 按画框去算 */}
        <img
          src={chosen ? chosen.portrait : leaf.src}
          alt={chosen ? chosen.name : t('profile.figureAlt')}
          width={chosen ? undefined : leaf.w}
          height={chosen ? undefined : leaf.h}
          className="h-full w-full object-contain"
        />
      </div>
      <figcaption className="mt-2 text-center text-[0.6875rem] leading-relaxed text-ink-400">
        {chosen ? (
          <>
            <span className="block text-[0.625rem] tracking-[0.22em] text-cinnabar-500">
              {t('profile.figure.picked')}
            </span>
            <span className="mt-1 block font-serif text-lg font-bold tracking-wide text-ink-800">
              {chosen.name}
            </span>
            {subtitle && <span className="mt-0.5 block text-xs text-ink-500">{subtitle}</span>}
            {chosen.credit && <span className="mt-1 block">{chosen.credit}</span>}
          </>
        ) : (
          <>
            <span className="block">{t(leaf.credit)}</span>
            <span className="block text-ink-300">{t('profile.figureSource')}</span>
          </>
        )}
      </figcaption>
    </figure>
  )
}

/** 一个分类的卡片：标题 + 该分类下的全部特征。 */
function CategoryCard({
  group,
  onDelete,
  cardRef,
}: {
  group: CategoryGroup
  onDelete: (trait: TraitItem) => void
  cardRef: (el: HTMLElement | null) => void
}) {
  const { lang, t } = useI18n()
  return (
    <article ref={cardRef} className="card animate-fade-up px-4 py-3.5">
      <h3 className="font-serif text-sm font-bold tracking-wide text-cinnabar-600">
        {traitCategory(group.category, lang)}
      </h3>
      <ul className="mt-2 space-y-3">
        {group.traits.map(trait => (
          <li key={trait.id}>
            <p className="break-words text-sm leading-relaxed text-ink-800">{trait.content}</p>
            {/* 依据要留着：画像最怕"它凭什么这么说"，这句话就是答案 */}
            {trait.evidence && (
              <p className="mt-1 break-words border-l-2 border-paper-300 pl-2 text-xs leading-relaxed text-ink-400">
                {t('profile.evidence', { text: trait.evidence })}
              </p>
            )}
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              <span className="text-ink-300">
                {t('profile.confidence', { percent: Math.round(trait.confidence * 100) })}
              </span>
              <button
                type="button"
                onClick={() => onDelete(trait)}
                className="rounded text-ink-300 transition-colors hover:text-cinnabar-600"
              >
                {t('profile.deleteTrait')}
              </button>
            </p>
          </li>
        ))}
      </ul>
    </article>
  )
}

export default function Profile() {
  const { lang, t } = useI18n()
  const [data, setData] = useState<ProfileResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  /** 工具栏下面那行状态话：正在归纳 / 这次新增了几条 / 正在评定 */
  const [note, setNote] = useState<string | null>(null)
  /** 后台自动动作每进页面只做一次，否则做完重新读取会再触发一轮。两条各记一个。 */
  const autoExtractRan = useRef(false)
  const autoFigureRan = useRef(false)

  const stageRef = useRef<HTMLDivElement>(null)
  const figureRef = useRef<HTMLDivElement>(null)
  const columnRefs = useRef<Record<Side, HTMLDivElement | null>>({ left: null, right: null })
  const cardRefs = useRef<Record<string, HTMLElement | null>>({})
  const [lines, setLines] = useState<LeadLine[]>([])

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
        pendingCount
          ? t('profile.autoExtracting', { count: pendingCount })
          : t('profile.extracting'),
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
  // 评定历史人物。**两件事排在同一个 effect 里，一件没做完就不开始下一件**：
  // 并行发出去不只是让上游吃两份负载，更糟的是会拿**旧画像**去评人——这次刚
  // 归纳出来的特征还没进库。
  //
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
  const columns = useMemo(() => {
    const half = Math.ceil(grouped.length / 2)
    return { left: grouped.slice(0, half), right: grouped.slice(half) }
  }, [grouped])

  // 量一次线。依赖里带上语言与形象：换语言标签会换行、换形象框也会变。
  useLayoutEffect(() => {
    function measure() {
      const stage = stageRef.current
      const figure = figureRef.current
      if (!stage || !figure) return

      const stageBox = stage.getBoundingClientRect()
      if (stageBox.width < LINES_MIN_WIDTH || stageBox.height === 0) {
        // 窄屏（或测试环境量不出尺寸）：牵引线没有意义，直接不画
        setLines(previous => (previous.length ? [] : previous))
        return
      }

      const figureBox = figure.getBoundingClientRect()
      const inset = figureBox.width * FIGURE_INSET
      const next: LeadLine[] = []

      for (const side of ['left', 'right'] as const) {
        const column = columnRefs.current[side]
        const columnBox = column?.getBoundingClientRect()
        for (const group of columns[side]) {
          const card = cardRefs.current[group.category]
          if (!card) continue
          const box = card.getBoundingClientRect()
          if (box.height === 0) continue

          // 按卡片在整列里的相对位置分配出发高度：线不会拧成一团
          const ratio =
            columnBox && columnBox.height > 0
              ? Math.min(
                  1,
                  Math.max(0, (box.top + box.height / 2 - columnBox.top) / columnBox.height),
                )
              : 0.5

          const startY =
            figureBox.top -
            stageBox.top +
            figureBox.height * (ANCHOR_TOP + (ANCHOR_BOTTOM - ANCHOR_TOP) * ratio)
          const startX =
            side === 'left'
              ? figureBox.left - stageBox.left + inset
              : figureBox.right - stageBox.left - inset
          const endX =
            side === 'left' ? box.right - stageBox.left : box.left - stageBox.left
          const endY = box.top - stageBox.top + box.height / 2
          const bend = (endX - startX) / 2

          next.push({
            key: `${side}:${group.category}`,
            d: `M ${startX} ${startY} C ${startX + bend} ${startY}, ${endX - bend} ${endY}, ${endX} ${endY}`,
            fromX: startX,
            fromY: startY,
            toX: endX,
            toY: endY,
          })
        }
      }
      setLines(next)
    }

    measure()
    const stage = stageRef.current
    // jsdom 里没有 ResizeObserver，退回 window 的 resize
    if (!stage || typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }
    const observer = new ResizeObserver(measure)
    observer.observe(stage)
    return () => observer.disconnect()
  }, [columns, lang, data?.avatar])

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

  async function clearAll() {
    if (!window.confirm(t('profile.confirmClear'))) return
    try {
      await api.clearProfile()
      setNote(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('profile.deleteFailed'))
    }
  }

  const unavailable = data !== null && !data.available
  const avatar = data?.avatar ?? 'male'
  const figure = data?.figure ?? NO_FIGURE
  /** 评出来了才换人；名录里查不到（用户改了名录）也退回册页，不留一个空画框。 */
  const chosen = figure.id ? figure : null

  return (
    <section className="mx-auto w-full max-w-5xl">
      <PageHeader title={t('profile.title')} description={t('profile.description')}>
        {data !== null && data.total > 0 && (
          <Button variant="secondary" size="sm" onClick={clearAll}>
            {t('profile.clear')}
          </Button>
        )}
        <Button size="sm" onClick={() => void runExtract()} disabled={busy}>
          {busy ? t('profile.extracting') : t('profile.extract')}
        </Button>
      </PageHeader>

      {unavailable && <ErrorBox message={t('profile.unavailable', { error: data.error })} />}

      {loading && <Loading text={t('profile.loading')} />}
      {error && <ErrorBox message={error} />}

      {!loading && !unavailable && (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2">
            <Segmented
              value={avatar}
              ariaLabel={t('profile.avatarGroup')}
              onChange={value => void pickAvatar(value)}
              options={[
                { value: 'male' as const, label: t('profile.avatar.male') },
                { value: 'female' as const, label: t('profile.avatar.female') },
              ]}
            />
            <p className="text-sm text-ink-500">
              {t('profile.total', { count: data?.total ?? 0 })}
              {data !== null && data.pending > 0 && (
                <>
                  <span aria-hidden="true" className="mx-2 text-paper-400">
                    ·
                  </span>
                  {t('profile.pending', { count: data.pending })}
                </>
              )}
            </p>
          </div>

          {note && (
            <p className="mb-5 flex items-center gap-2 text-sm text-ink-500">
              {busy && (
                <span
                  aria-hidden="true"
                  className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-paper-300 border-t-cinnabar-500"
                />
              )}
              {note}
            </p>
          )}

          {/* 舞台：牵引线画在整个舞台上，卡片与形象各自排在三栏里。
              线在 DOM 里排在网格**前面**，因此落在卡片之下——只在边缘相接，
              不会横穿字。 */}
          <div ref={stageRef} className="relative">
            <svg
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 h-full w-full"
            >
              {lines.map(line => (
                <g key={line.key} className="animate-fade-in">
                  <path
                    d={line.d}
                    fill="none"
                    strokeWidth="1.5"
                    className="stroke-cinnabar-300"
                  />
                  <circle cx={line.fromX} cy={line.fromY} r="2.5" className="fill-cinnabar-400" />
                  <circle cx={line.toX} cy={line.toY} r="3" className="fill-cinnabar-400" />
                </g>
              ))}
            </svg>

            <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
              <div
                ref={el => {
                  columnRefs.current.left = el
                }}
                className="space-y-4"
              >
                {columns.left.map(group => (
                  <CategoryCard
                    key={group.category}
                    group={group}
                    onDelete={removeTrait}
                    cardRef={el => {
                      cardRefs.current[group.category] = el
                    }}
                  />
                ))}
              </div>

              {/* 窄屏折成一栏时形象排在最前：它是这一页的主角，
                  排在两列卡片下面就很难注意到 */}
              <div className="order-first mx-auto w-40 self-start sm:w-48 md:order-none lg:w-60">
                <Figure avatar={avatar} chosen={chosen} boxRef={figureRef} />
              </div>

              <div
                ref={el => {
                  columnRefs.current.right = el
                }}
                className="space-y-4"
              >
                {columns.right.map(group => (
                  <CategoryCard
                    key={group.category}
                    group={group}
                    onDelete={removeTrait}
                    cardRef={el => {
                      cardRefs.current[group.category] = el
                    }}
                  />
                ))}
              </div>
            </div>
          </div>

          {grouped.length === 0 && (
            <div className="mt-2">
              <Empty>{t('profile.empty')}</Empty>
              <p className="text-center text-sm text-ink-400">{t('profile.emptyHint')}</p>
            </div>
          )}

          {/* 题跋：像在哪里。放在整个舞台下面而不是挤进中间那一栏——
              理由要两三句话才说得清，画框边上那点宽度写不下。 */}
          {chosen && (
            <section className="mx-auto mt-10 max-w-2xl text-center">
              {chosen.reason && (
                <>
                  <h3 className="font-serif text-sm font-bold tracking-[0.22em] text-cinnabar-600">
                    {t('profile.figure.reason')}
                  </h3>
                  <p className="mt-3 font-serif text-[0.9375rem] leading-loose text-ink-800">
                    {chosen.reason}
                  </p>
                </>
              )}
              <p className="mt-3 text-xs text-ink-400">
                {t('profile.figure.meta', {
                  date: chosen.chosen_at,
                  count: chosen.pool_size,
                })}
              </p>
              <div className="mt-4">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void runFigure()}
                  disabled={busy}
                >
                  {busy ? t('profile.figure.evaluating') : t('profile.figure.evaluate')}
                </Button>
              </div>
            </section>
          )}

          {/* 名录空着时说一句，而不是让页面永远停在册页上让人以为没做完 */}
          {!chosen && figure.pool_size === 0 && (
            <p className="mt-6 text-center text-xs text-ink-400">{t('profile.figure.none')}</p>
          )}

          {grouped.length > 0 && (
            <p className="mt-8 text-center text-xs text-ink-400">{t('profile.footnote')}</p>
          )}
        </>
      )}
    </section>
  )
}

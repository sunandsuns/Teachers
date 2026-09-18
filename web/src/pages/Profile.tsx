/** 「画像」页面：从你自己问过的话里，慢慢拼出的"你是谁"。
 *
 * 两条不变的契约（别的都是排版）：
 *
 * 1. **归纳是异步的，不能挡住首屏**。一次归纳要走一趟模型，几十秒起步。所以
 *    进页面先渲染已有画像，发现"还有没归纳过的新提问"再在后台补一次——
 *    让用户对着空白页面等半分钟，比给他一份旧画像还难受。
 * 2. **没有特征不等于出错**。还没有提问、模型不可用、模型这次没读出东西，
 *    都是正常状态，各自说明原因即可，不要弹红色报错——用户会以为功能坏了。
 *
 * 关于形象与牵引线
 * --------------------------------------------------------------------------
 * 形象用的是**真实的古画**：明·陈洪绶《仿古图册》里的两页——陶渊明像配男式，
 * 仕女图配女式。同一个册子、同一种绢底、同一路笔法，两式放在一起才像一对。
 * 出处是克利夫兰艺术博物馆的开放数据（CC0）。图片存 `src/assets/`，**只裁到画心**
 * （四边的装裱一律不进图，否则会留一条浅色亮带）；两幅画心比例不同，差额交给
 * 容器的 `object-contain` + `paper-200` 底色去补，看着就是装裱。
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

/**
 * 两式形象的画心。
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
 * 形象：一页册页，男女各一幅。
 *
 * 两式的差别落在**画本身**——陶渊明是执杖的士人，仕女是低眉回身的女子——
 * 不靠颜色或符号去区分，那样会把"这是谁"变成"这是个什么标签"。
 *
 * ``boxRef`` 只挂在**画心那一层**上（不含题签）：牵引线是量它的边框来定位的。
 */
function Figure({ avatar, boxRef }: { avatar: Avatar; boxRef: Ref<HTMLDivElement> }) {
  const { t } = useI18n()
  const { src, w, h, credit } = FIGURES[avatar]

  return (
    <figure className="w-full">
      <div
        ref={boxRef}
        className="aspect-portrait w-full overflow-hidden rounded-sm bg-paper-200 shadow-leaf ring-1 ring-paper-300"
      >
        <img
          src={src}
          alt={t('profile.figureAlt')}
          width={w}
          height={h}
          className="h-full w-full object-contain"
        />
      </div>
      <figcaption className="mt-2 text-center text-[0.6875rem] leading-relaxed text-ink-400">
        <span className="block">{t(credit)}</span>
        <span className="block text-ink-300">{t('profile.figureSource')}</span>
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
  /** 工具栏下面那行状态话：正在归纳 / 这次新增了几条 */
  const [note, setNote] = useState<string | null>(null)
  /** 自动归纳每进页面只做一次，否则归纳完重新读取会再触发一轮 */
  const autoRan = useRef(false)

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

  // 进页面时若发现"问过话但还没归纳过"，顺手在后台补一次。
  // 不等它：页面照常渲染已有的画像。
  useEffect(() => {
    if (loading || !data || autoRan.current) return
    if (!data.available || data.pending === 0) return
    autoRan.current = true
    void runExtract(data.pending)
  }, [loading, data, runExtract])

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
                <Figure avatar={avatar} boxRef={figureRef} />
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

          {grouped.length > 0 && (
            <p className="mt-8 text-center text-xs text-ink-400">{t('profile.footnote')}</p>
          )}
        </>
      )}
    </section>
  )
}

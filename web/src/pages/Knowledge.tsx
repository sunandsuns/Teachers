import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  api,
  type KbEdge,
  type KbEdgeKind,
  type KbGraph,
  type KbLink,
  type KbNode,
  type KbNodeDetail,
} from '../api/client'
import { bookTitle, categoryName, themeName, useI18n } from '../i18n'
import PageHeader from '../components/ui/PageHeader'
import Segmented from '../components/ui/Segmented'
import Chip from '../components/ui/Chip'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import { Empty, ErrorBox, Loading } from '../components/Status'
import { edgeKey, layoutGraph, neighbourhood, nodeRadius } from '../lib/graph'
import { useAsync } from '../hooks/useAsync'

/** 画布的逻辑尺寸。定值而非量取实际像素：布局是确定性的，
 *  换屏幕只会等比缩放，不会换个形状。
 *
 *  比例接近 1.16:1 而不是常见的 1.4:1：布局是三层同心环，等比缩放下
 *  画布越高圆越大。太扁的画布会把环缩到中间一小块，两侧白白空着。 */
const VIEW_W = 720
const VIEW_H = 620

/** 图上显示哪些节点。`all` 是书 + 主题，`book` 只有书——后者看得见纯互参结构。 */
type Scope = 'all' | 'book'

/** 三种边的画法。互参是实线（作者明写的对照），主题是虚线（归属），
 *  章节是更淡的点线（构成关系，不是引用）。 */
const EDGE_STYLE: Record<KbEdgeKind, string> = {
  cross: 'stroke-ink-400',
  theme: 'stroke-celadon-300',
  part: 'stroke-paper-400',
}

const EDGE_DASH: Record<KbEdgeKind, string | undefined> = {
  cross: undefined,
  theme: '5 4',
  part: '2 4',
}

const NODE_FILL: Record<string, string> = {
  theme: 'fill-cinnabar-500',
  book: 'fill-ink-700',
  chapter: 'fill-paper-400',
}

const NODE_RING: Record<string, string> = {
  theme: 'stroke-cinnabar-200',
  book: 'stroke-ink-300',
  chapter: 'stroke-paper-300',
}

function edgeWidth(edge: KbEdge): number {
  return edge.kind === 'cross' ? 1 + Math.min(edge.weight, 4) * 0.18 : 1
}

/** 按范围过滤节点；两端不都在可见集合里的边一并去掉，免得留下悬空的线。 */
function applyScope(graph: KbGraph, scope: Scope): KbGraph {
  if (scope === 'all') return graph
  const nodes = graph.nodes.filter(n => n.kind === 'book' || n.kind === 'chapter')
  const ids = new Set(nodes.map(n => n.id))
  return {
    ...graph,
    nodes,
    edges: graph.edges.filter(e => ids.has(e.source) && ids.has(e.target)),
  }
}

function statNumber(graph: KbGraph | null, key: string): number {
  const value = graph?.stats?.[key]
  return typeof value === 'number' ? value : 0
}

/** 三类节点的图例/无障碍名称。 */
const KIND_LABEL_KEY = {
  book: 'kb.legend.book',
  theme: 'kb.legend.theme',
  chapter: 'kb.legend.chapter',
} as const

/** 边类型的显示名。 */
const EDGE_LABEL_KEY = {
  theme: 'kb.kind.theme',
  cross: 'kb.kind.cross',
  part: 'kb.kind.part',
} as const

export default function Knowledge() {
  const { t, lang } = useI18n()
  const navigate = useNavigate()

  const [scope, setScope] = useState<Scope>('all')
  const [chapters, setChapters] = useState(false)
  const [focus, setFocus] = useState<string | null>(null)
  const [hover, setHover] = useState<string | null>(null)

  const { data: fullGraph, error: fullError, loading } = useAsync<KbGraph>(
    () => api.kbGraph(chapters),
    [chapters],
  )

  // 聚焦节点后另取两张数据：图（局部）与详情（双链）。两者一起取，
  // 否则会出现"图已经切过去了、右侧还写着上一个节点"的错位。
  const [localGraph, setLocalGraph] = useState<KbGraph | null>(null)
  const [detail, setDetail] = useState<KbNodeDetail | null>(null)
  const [focusFailed, setFocusFailed] = useState(false)
  const [focusLoading, setFocusLoading] = useState(false)

  useEffect(() => {
    if (!focus) {
      setLocalGraph(null)
      setDetail(null)
      setFocusFailed(false)
      return
    }
    let cancelled = false
    setFocusLoading(true)
    setFocusFailed(false)
    Promise.all([api.kbNode(focus), api.kbLocal(focus, chapters)])
      .then(([nodeDetail, local]) => {
        if (cancelled) return
        setDetail(nodeDetail)
        setLocalGraph(local)
      })
      .catch(() => {
        if (!cancelled) setFocusFailed(true)
      })
      .finally(() => {
        if (!cancelled) setFocusLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [focus, chapters])

  const base = focus ? localGraph : fullGraph
  const visible = useMemo(() => (base ? applyScope(base, scope) : null), [base, scope])

  const positions = useMemo(() => {
    if (!visible) return new Map<string, { x: number; y: number }>()
    return layoutGraph(visible.nodes, visible.edges, {
      width: VIEW_W,
      height: VIEW_H,
    })
  }, [visible])

  /** 高亮的依据：优先看鼠标悬停，其次看当前焦点。 */
  const highlight = useMemo(() => {
    if (!visible) return { nodes: new Set<string>(), edges: new Set<string>() }
    return neighbourhood(visible.edges, hover ?? focus)
  }, [visible, hover, focus])

  const selectNode = useCallback(
    (nodeId: string) => {
      // 再点一次同一个节点 = 回到全图。比另加一个"取消"按钮好在
      // 手上不用挪位置，这也是 Obsidian 里点空白处的等价操作
      setFocus(current => (current === nodeId ? null : nodeId))
      setHover(null)
    },
    [],
  )

  const openNode = useCallback(
    (node: KbNode) => {
      if (node.kind === 'book') {
        navigate(`/books/${node.meta.book_id ?? ''}`)
      } else if (node.kind === 'chapter') {
        navigate(`/books/${node.meta.book_id ?? ''}?chapter=${node.meta.chapter_id ?? ''}`)
      }
    },
    [navigate],
  )

  const labelled = (visible?.nodes.length ?? 0) <= 60
  const focusedNode = detail?.node ?? visible?.nodes.find(n => n.id === focus) ?? null

  return (
    <div>
      <PageHeader
        title={t('kb.title')}
        description={t('kb.description', {
          books: statNumber(fullGraph, 'books'),
          themes: statNumber(fullGraph, 'themes'),
          edges: statNumber(fullGraph, 'edges'),
        })}
      />

      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-3">
        <Segmented<Scope>
          value={scope}
          onChange={setScope}
          ariaLabel={t('kb.scopeGroup')}
          options={[
            { value: 'all', label: t('kb.scope.all') },
            { value: 'book', label: t('kb.scope.book') },
          ]}
        />
        <Chip
          active={chapters}
          onClick={() => setChapters(value => !value)}
          title={t('kb.chaptersHint')}
        >
          {t('kb.chapters')}
        </Chip>

        <ul className="flex items-center gap-3.5 text-xs text-ink-500">
          <LegendItem className="fill-cinnabar-500" label={t('kb.legend.theme')} />
          <LegendItem className="fill-ink-700" label={t('kb.legend.book')} />
          <LegendItem className="fill-paper-400" label={t('kb.legend.chapter')} />
        </ul>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <section className="card p-3">
          {loading && !fullGraph ? (
            <Loading />
          ) : fullError ? (
            <ErrorBox message={`${t('kb.loadFailed')}：${fullError}`} />
          ) : !visible || visible.nodes.length === 0 ? (
            <Empty>{t('kb.scopeUnavailable')}</Empty>
          ) : (
            <svg
              viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
              className="w-full"
              role="img"
              aria-label={t('kb.canvasLabel')}
            >
              <g>
                {visible.edges.map(edge => {
                  const from = positions.get(edge.source)
                  const to = positions.get(edge.target)
                  if (!from || !to) return null
                  const active = highlight.edges.has(edgeKey(edge))
                  const faded = !!hover && !active
                  return (
                    <line
                      key={edgeKey(edge)}
                      x1={from.x}
                      y1={from.y}
                      x2={to.x}
                      y2={to.y}
                      strokeWidth={active ? edgeWidth(edge) + 0.6 : edgeWidth(edge)}
                      strokeDasharray={EDGE_DASH[edge.kind]}
                      className={`${active ? 'stroke-cinnabar-500' : EDGE_STYLE[edge.kind]} ${
                        faded ? 'opacity-15' : 'opacity-80'
                      } transition-opacity`}
                    />
                  )
                })}
              </g>

              <g>
                {visible.nodes.map(node => {
                  const point = positions.get(node.id)
                  if (!point) return null
                  const radius = nodeRadius(node)
                  const active = highlight.nodes.has(node.id)
                  const faded = !!hover && !active
                  // 章节有几百个，标签全画出来会糊成一团黑；只在它被指到或
                  // 整张图本来就很小的时候才显示
                  const showLabel =
                    node.kind !== 'chapter' || active || node.id === focus || labelled
                  return (
                    <g
                      key={node.id}
                      role="button"
                      tabIndex={0}
                      aria-label={`${node.label}（${t(KIND_LABEL_KEY[node.kind as keyof typeof KIND_LABEL_KEY] ?? 'kb.legend.book')}）`}
                      aria-pressed={node.id === focus}
                      className="cursor-pointer focus-visible:outline-none"
                      onMouseEnter={() => setHover(node.id)}
                      onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover(node.id)}
                      onBlur={() => setHover(null)}
                      onClick={() => selectNode(node.id)}
                      onKeyDown={event => {
                        if (event.key !== 'Enter' && event.key !== ' ') return
                        event.preventDefault()
                        selectNode(node.id)
                      }}
                    >
                      <circle
                        cx={point.x}
                        cy={point.y}
                        r={radius}
                        strokeWidth={node.id === focus ? 2.5 : 1.5}
                        className={`${NODE_FILL[node.kind] ?? 'fill-ink-700'} ${
                          node.id === focus
                            ? 'stroke-cinnabar-500'
                            : NODE_RING[node.kind] ?? 'stroke-ink-300'
                        }`}
                        opacity={faded ? 0.18 : 1}
                      />
                      {showLabel && (
                        <text
                          x={point.x}
                          y={point.y - radius - 4}
                          textAnchor="middle"
                          className={`pointer-events-none font-sans text-[10px] ${
                            active || node.id === focus ? 'fill-ink-900' : 'fill-ink-500'
                          }`}
                          opacity={faded ? 0.2 : 1}
                        >
                          {node.kind === 'book'
                            ? bookTitle(node.label, lang)
                            : node.kind === 'theme'
                              ? themeName(node.label, lang)
                              : node.label}
                        </text>
                      )}
                    </g>
                  )
                })}
              </g>
            </svg>
          )}

          <p className="mt-2 px-1 text-xs text-ink-400">{t('kb.legend.hint')}</p>
        </section>

        <aside className="space-y-4">
          <SearchBox onPick={selectNode} />

          {focus && focusLoading && <Loading />}
          {focus && focusFailed && <ErrorBox message={t('kb.loadFailed')} />}

          {!focus ? (
            <div className="card p-4">
              <p className="font-serif text-sm leading-relaxed text-ink-500">
                {t('kb.pickHint')}
              </p>
            </div>
          ) : (
            focusedNode && (
              <>
                <NodeCard node={focusedNode} onOpen={openNode} onBack={() => setFocus(null)} />
                <LinkList
                  title={t('kb.link.outgoing')}
                  empty={t('kb.link.noneOutgoing')}
                  links={detail?.outgoing ?? []}
                  onPick={selectNode}
                  activeId={hover}
                  onHover={setHover}
                />
                <LinkList
                  title={t('kb.link.backlinks')}
                  empty={t('kb.link.noneBacklinks')}
                  links={detail?.backlinks ?? []}
                  onPick={selectNode}
                  activeId={hover}
                  onHover={setHover}
                />
                {detail && detail.theme_rows.length > 0 && (
                  <ThemeRows detail={detail} />
                )}
                {detail && detail.cross_refs.length > 0 && (
                  <CrossRefList detail={detail} />
                )}
              </>
            )
          )}
        </aside>
      </div>
    </div>
  )
}

// ── 图例 ────────────────────────────────────────────────────────────────

function LegendItem({ className, label }: { className: string; label: string }) {
  return (
    <li className="inline-flex items-center gap-1.5">
      <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${className}`} />
      {label}
    </li>
  )
}

// ── 搜索 ────────────────────────────────────────────────────────────────

/** 按名字跳节点。走的是后端检索而不是在已加载的图上做本地过滤——
 *  因为"章节"这类节点平时并不在图里，本地过滤就找不到了。 */
function SearchBox({ onPick }: { onPick: (nodeId: string) => void }) {
  const { t, lang } = useI18n()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<KbNode[] | null>(null)
  const [failed, setFailed] = useState(false)

  const submit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault()
      setFailed(false)
      try {
        const hits = await api.kbSearch(query)
        setResults(hits)
      } catch {
        setFailed(true)
      }
    },
    [query],
  )

  const pick = useCallback(
    (node: KbNode) => {
      onPick(node.id)
      setResults(null)
      setQuery('')
    },
    [onPick],
  )

  return (
    // role="search" 落在整块上而不是 <form> 上：检索结果也属于"搜索区"，
    // 读屏软件跳到这里时该一并看到命中列表
    <div className="card p-4" role="search">
      <form onSubmit={submit} className="flex items-center gap-2">
        <label htmlFor="kb-search" className="sr-only">
          {t('kb.searchLabel')}
        </label>
        <input
          id="kb-search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder={t('kb.searchPlaceholder')}
          className="field min-w-0 flex-1"
        />
        <Button type="submit" size="sm" variant="secondary">
          {t('kb.searchSubmit')}
        </Button>
      </form>

      {failed && <p className="mt-2 text-xs text-cinnabar-600">{t('kb.loadFailed')}</p>}

      {results !== null &&
        (results.length === 0 ? (
          <p className="mt-2 text-xs text-ink-400">{t('kb.searchEmpty')}</p>
        ) : (
          <ul className="mt-2 space-y-0.5">
            {results.map(node => (
              <li key={node.id}>
                <button
                  type="button"
                  onClick={() => pick(node)}
                  className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm text-ink-700 hover:bg-paper-200"
                >
                  <span className="truncate">
                    {node.kind === 'book'
                      ? bookTitle(node.label, lang)
                      : node.kind === 'theme'
                        ? themeName(node.label, lang)
                        : node.label}
                  </span>
                  <span className="shrink-0 text-xs text-ink-400">
                    {t('kb.meta.degree', { count: node.degree })}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ))}
    </div>
  )
}

// ── 节点卡片 ────────────────────────────────────────────────────────────

function NodeCard({
  node,
  onOpen,
  onBack,
}: {
  node: KbNode
  onOpen: (node: KbNode) => void
  onBack: () => void
}) {
  const { t, lang } = useI18n()
  const isBook = node.kind === 'book'
  const isTheme = node.kind === 'theme'

  const title = isBook
    ? bookTitle(node.label, lang)
    : isTheme
      ? themeName(node.label, lang)
      : node.label

  return (
    <div className="card p-4">
      <div className="mb-2 flex items-start justify-between gap-3">
        <h2 className="font-serif text-lg font-bold leading-snug text-ink-900">{title}</h2>
        <Badge tone={isTheme ? 'brand' : isBook ? 'ink' : 'neutral'}>
          {isTheme ? t('kb.legend.theme') : isBook ? t('kb.legend.book') : t('kb.legend.chapter')}
        </Badge>
      </div>

      <dl className="space-y-1 text-xs text-ink-500">
        {isBook && (
          <>
            <MetaRow label={t('kb.meta.author')} value={node.meta.author ?? ''} />
            <MetaRow
              label={t('kb.meta.category')}
              value={node.meta.category ? categoryName(node.meta.category, lang) : ''}
            />
            <MetaRow
              label={t('kb.meta.chapters')}
              value={node.meta.chapter_count !== undefined ? `${node.meta.chapter_count}` : ''}
            />
            <MetaRow
              label={t('kb.meta.source')}
              value={node.meta.has_source ? t('kb.meta.hasSource') : t('kb.meta.noSource')}
            />
          </>
        )}
        {node.kind === 'chapter' && node.meta.book_title && (
          <MetaRow label={t('kb.legend.book')} value={bookTitle(node.meta.book_title, lang)} />
        )}
        <MetaRow label="" value={t('kb.meta.degree', { count: node.degree })} />
      </dl>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {(isBook || node.kind === 'chapter') && (
          <Button size="sm" onClick={() => onOpen(node)}>
            {node.kind === 'chapter' ? t('kb.openChapter') : t('kb.read')}
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onBack}>
          {t('kb.backToFull')}
        </Button>
      </div>
    </div>
  )
}

function MetaRow({ label, value }: { label: string; value: string }) {
  if (!value) return null
  return (
    <div className="flex gap-2">
      {label && <dt className="shrink-0 text-ink-400">{label}</dt>}
      <dd className="min-w-0 text-ink-600">{value}</dd>
    </div>
  )
}

// ── 双链列表 ────────────────────────────────────────────────────────────

function LinkList({
  title,
  empty,
  links,
  onPick,
  activeId,
  onHover,
}: {
  title: string
  empty: string
  links: KbLink[]
  onPick: (nodeId: string) => void
  activeId: string | null
  onHover: (nodeId: string | null) => void
}) {
  const { t, lang } = useI18n()

  return (
    <div className="card p-4">
      <h3 className="mb-2 flex items-center justify-between text-xs font-medium text-ink-500">
        {title}
        <span className="text-ink-400">{links.length}</span>
      </h3>
      {links.length === 0 ? (
        <p className="text-xs text-ink-400">{empty}</p>
      ) : (
        <ul className="space-y-0.5">
          {links.map(link => (
            <li key={`${link.direction}-${link.kind}-${link.node_id}`}>
              <button
                type="button"
                onClick={() => onPick(link.node_id)}
                onMouseEnter={() => onHover(link.node_id)}
                onMouseLeave={() => onHover(null)}
                className={`w-full rounded-md px-2 py-1.5 text-left transition-colors ${
                  activeId === link.node_id ? 'bg-paper-200' : 'hover:bg-paper-200'
                }`}
              >
                <span className="flex items-center gap-2">
                  <span className="truncate font-serif text-sm text-ink-800">
                    {bookTitle(link.label, lang)}
                  </span>
                  <span className="shrink-0 text-[10px] text-ink-400">
                    {t(EDGE_LABEL_KEY[link.kind])}
                  </span>
                </span>
                {link.edge_label && (
                  <span className="mt-0.5 line-clamp-2 block text-xs leading-relaxed text-ink-500">
                    {link.edge_label}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── 主题明细 / 互参原文 ─────────────────────────────────────────────────

function ThemeRows({ detail }: { detail: KbNodeDetail }) {
  const { t, lang } = useI18n()
  const isBook = detail.node.kind === 'book'

  return (
    <div className="card p-4">
      <h3 className="mb-2 text-xs font-medium text-ink-500">{t('kb.themeRows')}</h3>
      <ul className="space-y-2.5">
        {detail.theme_rows.map(row => (
          <li key={`${row.book_id}-${row.theme}`}>
            <p className="text-xs text-ink-400">
              {isBook
                ? themeName(row.theme, lang)
                : `${bookTitle(row.book_title, lang)} · ${themeName(row.theme, lang)}`}
            </p>
            <p className="text-sm leading-relaxed text-ink-700">{row.judgment}</p>
            {row.quote && (
              <p className="mt-0.5 font-kai text-xs text-ink-500">{row.quote}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function CrossRefList({ detail }: { detail: KbNodeDetail }) {
  const { t } = useI18n()
  return (
    <div className="card p-4">
      <h3 className="mb-2 text-xs font-medium text-ink-500">{t('kb.crossRefs')}</h3>
      <ul className="space-y-2">
        {detail.cross_refs.map(ref => (
          <li key={ref.name} className="text-xs leading-relaxed text-ink-600">
            <span className="font-serif text-ink-800">与《{ref.name}》</span>：{ref.detail}
          </li>
        ))}
      </ul>
    </div>
  )
}

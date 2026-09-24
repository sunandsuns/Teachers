import type { KbGraph } from '../../api/client'
import { Empty, Skeleton } from '../../components/ui'
import { ErrorBox } from '../../components/Status'
import { useI18n } from '../../i18n'
import { edgeKey, nodeRadius } from '../../lib/graph'
import {
  EDGE_DASH,
  EDGE_STYLE,
  KIND_LABEL_KEY,
  NODE_FILL,
  NODE_RING,
  VIEW_H,
  VIEW_W,
  edgeWidth,
  nodeLabel,
} from './constants'

/**
 * 关系图。
 *
 * 四种状态各有各的处理，顺序即优先级：
 *   首次载入 → 骨架（画布尺寸是已知的定值，撑出来就不会跳）
 *   出错     → 错误框
 *   空       → 说明"这个筛选下没有节点"
 *   有图     → SVG
 *
 * 骨架而不是转圈：画布的宽高比是常量（720×620），版面完全可预测。
 * 反过来，寻章的检索结果就不知道会来几条，那里才该用转圈。
 *
 * 无障碍上每个节点是一个 `role="button"` 的 `<g>`，名字是「书名（类型）」——
 * 图上画的是圆和线，读屏软件必须能听到"这是什么、属于哪一类"。
 * 键盘可达（tabIndex + Enter/Space），否则纯键盘用户根本进不了这张图。
 */
export default function GraphCanvas({
  visible,
  positions,
  highlight,
  hover,
  focus,
  labelled,
  loading,
  error,
  onSelect,
  onHover,
}: {
  visible: KbGraph | null
  positions: Map<string, { x: number; y: number }>
  highlight: { nodes: Set<string>; edges: Set<string> }
  hover: string | null
  focus: string | null
  labelled: boolean
  loading: boolean
  error: string | null
  onSelect: (nodeId: string) => void
  onHover: (nodeId: string | null) => void
}) {
  const { lang, t } = useI18n()

  return (
    <section className="card p-3">
      {loading && !visible ? (
        <div style={{ aspectRatio: `${VIEW_W} / ${VIEW_H}` }} className="w-full">
          <Skeleton className="h-full w-full rounded-lg" />
        </div>
      ) : error ? (
        <ErrorBox message={`${t('kb.loadFailed')}：${error}`} />
      ) : !visible || visible.nodes.length === 0 ? (
        <Empty title={t('kb.scopeUnavailable')} />
      ) : (
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className="w-full"
          role="img"
          aria-label={t('kb.canvasLabel')}
        >
          {/* 先画线再画点：线要从点底下穿过，反过来点会被线割开 */}
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
                  className={`transition-opacity duration-quick ease-swift ${
                    active ? 'stroke-cinnabar-500' : EDGE_STYLE[edge.kind]
                  } ${faded ? 'opacity-15' : 'opacity-80'}`}
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
              const selected = node.id === focus
              // 章节有几百个，标签全画出来会糊成一团黑；只在它被指到或
              // 整张图本来就很小的时候才显示
              const showLabel = node.kind !== 'chapter' || active || selected || labelled

              return (
                <g
                  key={node.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`${nodeLabel(node, lang)}（${t(
                    KIND_LABEL_KEY[node.kind as keyof typeof KIND_LABEL_KEY] ?? 'kb.legend.book',
                  )}）`}
                  aria-pressed={selected}
                  // 焦点可见性必须**画在 SVG 里**：全局那条 `:focus-visible`
                  // 用的是 box-shadow 焦点环，而 box-shadow 对 SVG 子元素不生效——
                  // 只写 outline-none 的话，键盘 Tab 过来是完全看不出来的。
                  // 所以聚焦时把圆点的描边换成朱砂并加粗，用图形本身当焦点指示。
                  className="cursor-pointer focus-visible:outline-none [&:focus-visible>circle]:stroke-cinnabar-500 [&:focus-visible>circle]:stroke-[3px]"
                  onMouseEnter={() => onHover(node.id)}
                  onMouseLeave={() => onHover(null)}
                  onFocus={() => onHover(node.id)}
                  onBlur={() => onHover(null)}
                  onClick={() => onSelect(node.id)}
                  onKeyDown={event => {
                    if (event.key !== 'Enter' && event.key !== ' ') return
                    event.preventDefault()
                    onSelect(node.id)
                  }}
                >
                  {/* 焦点光晕：画在主圆之前，所以是"垫在下面"的一圈浅色。
                      比只把描边加粗更容易在密集的图里一眼找到当前节点 */}
                  {selected && (
                    <circle
                      cx={point.x}
                      cy={point.y}
                      r={radius + 7}
                      className="fill-cinnabar-200"
                      opacity={0.5}
                    />
                  )}

                  <circle
                    cx={point.x}
                    cy={point.y}
                    r={radius}
                    strokeWidth={selected ? 2.5 : 1.5}
                    className={`transition-opacity duration-quick ease-swift ${
                      NODE_FILL[node.kind] ?? 'fill-ink-700'
                    } ${selected ? 'stroke-cinnabar-500' : NODE_RING[node.kind] ?? 'stroke-ink-300'}`}
                    opacity={faded ? 0.18 : 1}
                  />

                  {showLabel && (
                    <text
                      x={point.x}
                      y={point.y - radius - 4}
                      textAnchor="middle"
                      // paintOrder + 描边：给文字垫一层纸色轮廓，压在线上也读得清。
                      // 不做这一步的话，穿过标签的边会把字切成两半
                      strokeWidth={3}
                      strokeLinejoin="round"
                      paintOrder="stroke"
                      className={`pointer-events-none font-sans text-[10px] stroke-paper-50 transition-opacity duration-quick ease-swift ${
                        active || selected ? 'fill-ink-900' : 'fill-ink-500'
                      }`}
                      opacity={faded ? 0.2 : 1}
                    >
                      {nodeLabel(node, lang)}
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
  )
}

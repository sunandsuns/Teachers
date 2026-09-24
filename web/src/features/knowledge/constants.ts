import type { KbEdge, KbEdgeKind, KbGraph } from '../../api/client'
import { bookTitle, themeName, type Lang } from '../../i18n'

/** 画布的逻辑尺寸。定值而非量取实际像素：布局是确定性的，
 *  换屏幕只会等比缩放，不会换个形状。
 *
 *  比例接近 1.16:1 而不是常见的 1.4:1：布局是三层同心环，等比缩放下
 *  画布越高圆越大。太扁的画布会把环缩到中间一小块，两侧白白空着。 */
export const VIEW_W = 720
export const VIEW_H = 620

/** 图上显示哪些节点。`all` 是书 + 主题，`book` 只有书——后者看得见纯互参结构。 */
export type Scope = 'all' | 'book'

/** 三种边的画法。互参是实线（作者明写的对照），主题是虚线（归属），
 *  章节是更淡的点线（构成关系，不是引用）。 */
export const EDGE_STYLE: Record<KbEdgeKind, string> = {
  cross: 'stroke-ink-400',
  theme: 'stroke-celadon-300',
  part: 'stroke-paper-400',
}

export const EDGE_DASH: Record<KbEdgeKind, string | undefined> = {
  cross: undefined,
  theme: '5 4',
  part: '2 4',
}

export const NODE_FILL: Record<string, string> = {
  theme: 'fill-cinnabar-500',
  book: 'fill-ink-700',
  chapter: 'fill-paper-400',
}

export const NODE_RING: Record<string, string> = {
  theme: 'stroke-cinnabar-200',
  book: 'stroke-ink-300',
  chapter: 'stroke-paper-300',
}

/** 三类节点的图例/无障碍名称。 */
export const KIND_LABEL_KEY = {
  book: 'kb.legend.book',
  theme: 'kb.legend.theme',
  chapter: 'kb.legend.chapter',
} as const

/** 边类型的显示名。 */
export const EDGE_LABEL_KEY = {
  theme: 'kb.kind.theme',
  cross: 'kb.kind.cross',
  part: 'kb.kind.part',
} as const

export function edgeWidth(edge: KbEdge): number {
  return edge.kind === 'cross' ? 1 + Math.min(edge.weight, 4) * 0.18 : 1
}

/** 按范围过滤节点；两端不都在可见集合里的边一并去掉，免得留下悬空的线。 */
export function applyScope(graph: KbGraph, scope: Scope): KbGraph {
  if (scope === 'all') return graph
  const nodes = graph.nodes.filter(n => n.kind === 'book' || n.kind === 'chapter')
  const ids = new Set(nodes.map(n => n.id))
  return {
    ...graph,
    nodes,
    edges: graph.edges.filter(e => ids.has(e.source) && ids.has(e.target)),
  }
}

export function statNumber(graph: KbGraph | null, key: string): number {
  const value = graph?.stats?.[key]
  return typeof value === 'number' ? value : 0
}

/** 节点标签：书与主题按当前语言显示，章节用原始标题。
 *
 *  抽出来是因为图上的 `<text>`、搜索命中、节点卡片三处都要同一套规则，
 *  各写一遍迟早会出现"图上叫 A、卡片上叫 B"。 */
export function nodeLabel(node: { kind: string; label: string }, lang: Lang): string {
  if (node.kind === 'book') return bookTitle(node.label, lang)
  if (node.kind === 'theme') return themeName(node.label, lang)
  return node.label
}

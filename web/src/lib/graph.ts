/** 关系图谱的布局算法。
 *
 * 纯函数：输入节点与边，输出每个节点的坐标。不碰 DOM、不碰 React，
 * 因此可以在 vitest 里直接验证"同一张图算两次结果一样"这类性质。
 *
 * 为什么自己写而不引 d3
 * --------------------------------------------------------------------------
 * 需要的只有"环 + 角度微调"这一点东西，d3-force 是 40KB 的通用解，
 * 而这里连半径都由我们自己定（见下）。与其为这点需求背一整个布局引擎，
 * 不如把这一百多行写清楚。
 *
 * 为什么是"半径固定、角度优化"
 * --------------------------------------------------------------------------
 * 纯力导向在这批数据上会把所有节点推成一团球：主题被书裹在中间，
 * "主题是最抽象的层、书在它外面"这个**本来就成立的层次**被抹掉了。
 * 所以这里换个思路——半径由节点类型直接决定，力导向只负责决定**角度**：
 *
 *     主题        内环     8 个，彼此等距
 *     经典        中环    15 部，按关系远近排开
 *     章节        外环    每章一望即知，围着自己的书成簇
 *
 * 于是斥力与引力只产生切向位移，层次感永远保留；同时"关系近的排得近"
 * 依然由边上的引力来实现。比纯力导向更可读，也更便宜（不必担心节点飞走）。
 *
 * 确定性
 * --------------------------------------------------------------------------
 * 种子角度由**节点 id 的稳定哈希**决定，迭代过程里没有任何随机数，
 * 所以同一张图每次算出来的坐标完全一致。这不是锦上添花：图谱在
 * 悬停、筛选、聚焦时都会重渲染，如果布局每算一次就换个样子，
 * 用户会看到整张图"抽搐"一下，之前记住的位置也全废了。
 */

export interface GraphNode {
  id: string
  kind: string
  label: string
  degree: number
}

export interface GraphEdge {
  source: string
  target: string
  kind: string
  label: string
  weight: number
}

export interface Point {
  x: number
  y: number
}

export interface LayoutOptions {
  width: number
  height: number
  /** 画布内边距（像素）。节点标签会画在圆外，留白不够会被裁掉 */
  padding?: number
  /** 迭代次数。省略时按规模自动取（大图少迭代，免得卡住首屏） */
  iterations?: number
}

/** 各类节点所在的环半径（占可用半径的比例）。 */
const RING_OF: Record<string, number> = {
  theme: 0.34,
  book: 0.74,
  chapter: 0.9,
}

/** 认不出的节点类型放哪儿。取最外环——总比让它压在中心好。 */
const FALLBACK_RING = 0.9

/** 稳定哈希（FNV-1a，32 位）→ [0, 1)。同 id 必得同值，与调用顺序无关。 */
export function hashUnit(id: string): number {
  let hash = 0x811c9dc5
  for (let i = 0; i < id.length; i += 1) {
    hash ^= id.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return ((hash >>> 0) % 100000) / 100000
}

/** 边的稳定标识。用来做 hover 高亮时的集合成员判断。 */
export function edgeKey(edge: GraphEdge): string {
  return `${edge.source}→${edge.target}:${edge.kind}`
}

/** 节点圆的半径：度数越高画得越大。
 *
 *  用平方根而不是线性：度数最高的节点（如《道德经》19 条）与最低的（1 条）
 *  相差近 20 倍，线性映射会让前者变成一颗巨球把旁边全压住。 */
export function nodeRadius(node: GraphNode): number {
  const base = node.kind === 'theme' ? 6 : node.kind === 'chapter' ? 2.5 : 5
  return base + Math.sqrt(Math.max(node.degree, 0)) * (node.kind === 'chapter' ? 0.6 : 2)
}

/** 与焦点直接相连的节点与边。用于「点一个节点，把它的关系点亮」。 */
export function neighbourhood(
  edges: GraphEdge[],
  focusId: string | null,
): { nodes: Set<string>; edges: Set<string> } {
  const nodes = new Set<string>()
  const keys = new Set<string>()
  if (!focusId) return { nodes, edges: keys }

  nodes.add(focusId)
  for (const edge of edges) {
    if (edge.source !== focusId && edge.target !== focusId) continue
    keys.add(edgeKey(edge))
    nodes.add(edge.source)
    nodes.add(edge.target)
  }
  return { nodes, edges: keys }
}

/** 布局：返回每个节点 id 对应的画布坐标。 */
export function layoutGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: LayoutOptions,
): Map<string, Point> {
  const { width, height, padding = 36 } = options
  const result = new Map<string, Point>()
  const count = nodes.length
  if (count === 0) return result

  const centreX = width / 2
  const centreY = height / 2
  const radius = Math.max(1, Math.min(width, height) / 2 - padding)

  const ringOf = (kind: string) => radius * (RING_OF[kind] ?? FALLBACK_RING)

  // ── 1. 播种 ────────────────────────────────────────────────────────
  const byKind = new Map<string, GraphNode[]>()
  for (const node of nodes) {
    const bucket = byKind.get(node.kind)
    if (bucket) bucket.push(node)
    else byKind.set(node.kind, [node])
  }

  /** 把一组节点均匀铺在一个环上。哈希只用来在各自的扇区里挪一点，
   *  避免每次都以正圆排布显得过于机械，又不至于串到相邻扇区里去。 */
  const placeRing = (group: GraphNode[], ringRadius: number) => {
    group.forEach((node, index) => {
      const angle =
        ((index + 0.15 + hashUnit(node.id) * 0.7) / group.length) * Math.PI * 2
      result.set(node.id, {
        x: centreX + Math.cos(angle) * ringRadius,
        y: centreY + Math.sin(angle) * ringRadius,
      })
    })
  }

  const themes = byKind.get('theme') ?? []
  const books = byKind.get('book') ?? []
  if (themes.length) placeRing(themes, ringOf('theme'))
  if (books.length) placeRing(books, ringOf('book'))

  // 章节与书之间只有一条构成边，没有任何横向关系，所以播种就让它们落在
  // **父书所在的那个方向**上——仿真只需微调角度，不必绕半圈才归位。
  const others = nodes.filter(node => node.kind !== 'theme' && node.kind !== 'book')
  if (others.length) {
    const parentOf = new Map<string, string>()
    for (const edge of edges) {
      if (edge.kind !== 'part') continue
      parentOf.set(edge.target, edge.source)
    }

    // 父节点（书）当前的种子角度
    const angleOf = new Map<string, number>()
    for (const [id, point] of result) {
      angleOf.set(id, Math.atan2(point.y - centreY, point.x - centreX))
    }

    for (const node of others) {
      const parent = parentOf.get(node.id)
      const parentAngle = parent ? angleOf.get(parent) : undefined
      const base = parentAngle ?? hashUnit(node.id) * Math.PI * 2
      // ±0.3 弧度：够散开，又不至于跑到邻座的书那边去
      const angle = base + (hashUnit(node.id) - 0.5) * 0.6
      const ring = ringOf(node.kind)
      result.set(node.id, {
        x: centreX + Math.cos(angle) * ring,
        y: centreY + Math.sin(angle) * ring,
      })
    }
  }

  // 兜底：万一有节点没被上面任何一支覆盖到（新增了节点类型忘了改这里），
  // 给个外环上的位置，别让后面读到 undefined 直接崩掉整页
  for (const node of nodes) {
    if (!result.has(node.id)) {
      const angle = hashUnit(node.id) * Math.PI * 2
      const ring = ringOf(node.kind)
      result.set(node.id, {
        x: centreX + Math.cos(angle) * ring,
        y: centreY + Math.sin(angle) * ring,
      })
    }
  }

  // ── 2. 只优化角度 ──────────────────────────────────────────────────
  const index = new Map<string, number>()
  nodes.forEach((node, i) => index.set(node.id, i))

  const targetRadius = new Float64Array(count)
  const xs = new Float64Array(count)
  const ys = new Float64Array(count)
  nodes.forEach((node, i) => {
    const point = result.get(node.id)!
    xs[i] = point.x
    ys[i] = point.y
    targetRadius[i] = ringOf(node.kind)
  })

  const links: [number, number, number][] = []
  for (const edge of edges) {
    const from = index.get(edge.source)
    const to = index.get(edge.target)
    if (from === undefined || to === undefined || from === to) continue
    links.push([from, to, Math.min(edge.weight, 4)])
  }

  const iterations = options.iterations ?? (count > 120 ? 60 : count > 40 ? 120 : 200)
  const ideal = Math.sqrt((width * height) / count)

  const dx = new Float64Array(count)
  const dy = new Float64Array(count)
  let temperature = radius * 0.35

  for (let step = 0; step < iterations; step += 1) {
    dx.fill(0)
    dy.fill(0)

    // 斥力：任意两点相斥。O(n²)，但 n 最多几百，且只算一次（不是每帧）
    for (let i = 0; i < count; i += 1) {
      for (let j = i + 1; j < count; j += 1) {
        let vx = xs[i] - xs[j]
        let vy = ys[i] - ys[j]
        let distance = Math.hypot(vx, vy)
        if (distance < 0.01) {
          // 完全重合：按 id 哈希给一个稳定的错开方向，不要用随机数
          const angle = hashUnit(nodes[i].id) * Math.PI * 2
          vx = Math.cos(angle) * 0.01
          vy = Math.sin(angle) * 0.01
          distance = 0.01
        }
        const force = (ideal * ideal) / distance
        const fx = (vx / distance) * force
        const fy = (vy / distance) * force
        dx[i] += fx
        dy[i] += fy
        dx[j] -= fx
        dy[j] -= fy
      }
    }

    // 引力：有边的两点相吸。权重高的边更紧，关系近的看起来就更近
    for (const [from, to, weight] of links) {
      const vx = xs[from] - xs[to]
      const vy = ys[from] - ys[to]
      const distance = Math.max(Math.hypot(vx, vy), 0.01)
      const force = ((distance * distance) / ideal) * 0.35 * (0.5 + weight * 0.25)
      const fx = (vx / distance) * force
      const fy = (vy / distance) * force
      dx[from] -= fx
      dy[from] -= fy
      dx[to] += fx
      dy[to] += fy
    }

    for (let i = 0; i < count; i += 1) {
      const length = Math.hypot(dx[i], dy[i])
      if (length < 0.0001) continue
      // 限幅：每一步最多走 temperature，随退火递减
      const scale = Math.min(length, temperature) / length
      xs[i] += dx[i] * scale
      ys[i] += dy[i] * scale
    }

    // 投影回各自的环上：位移里沿半径的那部分被丢掉，只保留转向。
    // 这一步就是"层次永远保留"的全部秘密，也省掉了向心力与防飞逸处理。
    for (let i = 0; i < count; i += 1) {
      const vx = xs[i] - centreX
      const vy = ys[i] - centreY
      const current = Math.hypot(vx, vy)
      if (current < 0.001) {
        const angle = hashUnit(nodes[i].id) * Math.PI * 2
        xs[i] = centreX + Math.cos(angle) * targetRadius[i]
        ys[i] = centreY + Math.sin(angle) * targetRadius[i]
        continue
      }
      const scale = targetRadius[i] / current
      xs[i] = centreX + vx * scale
      ys[i] = centreY + vy * scale
    }

    temperature *= 0.93
  }

  // ── 3. 撑满画布 ────────────────────────────────────────────────────
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (let i = 0; i < count; i += 1) {
    if (xs[i] < minX) minX = xs[i]
    if (xs[i] > maxX) maxX = xs[i]
    if (ys[i] < minY) minY = ys[i]
    if (ys[i] > maxY) maxY = ys[i]
  }

  const spanX = maxX - minX
  const spanY = maxY - minY
  const usableWidth = Math.max(1, width - padding * 2)
  const usableHeight = Math.max(1, height - padding * 2)

  // **等比**缩放，宁可左右留白也不把环拉扁：拉扁之后左右两侧的书会落到
  // 同一条水平线上，它们之间的互参边于是连成一整条横带穿过画面，
  // 既难看又盖住了中间的主题环。等比缩放保住的正是"三层同心"这个读法。
  // 某一维完全没跨度（只有一个节点）时取 1，节点于是落在正中。
  const scaleX = spanX > 1e-6 ? usableWidth / spanX : Number.POSITIVE_INFINITY
  const scaleY = spanY > 1e-6 ? usableHeight / spanY : Number.POSITIVE_INFINITY
  const rawScale = Math.min(scaleX, scaleY)
  const scale = Number.isFinite(rawScale) ? rawScale : 1

  const offsetX = (width - spanX * scale) / 2
  const offsetY = (height - spanY * scale) / 2

  nodes.forEach((node, i) => {
    result.set(node.id, {
      x: (xs[i] - minX) * scale + offsetX,
      y: (ys[i] - minY) * scale + offsetY,
    })
  })

  return result
}

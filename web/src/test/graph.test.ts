/** 图谱布局算法。
 *
 * 这一层是纯函数，所以能在这里钉住几条**性质**——比逐个断言坐标值可靠，
 * 也不会因为调了斥力系数就整片红。
 *
 * 最要紧的一条是**确定性**：同一张图必须每次算出同一份坐标。
 * 图谱会在悬停、筛选、聚焦时反复重算，只要结果不稳，用户就会看到
 * 整张图"抽搐"，之前记住的位置也全废了。
 */

import { describe, expect, it } from 'vitest'
import {
  edgeKey,
  hashUnit,
  layoutGraph,
  neighbourhood,
  nodeRadius,
  type GraphEdge,
  type GraphNode,
} from '../lib/graph'

const WIDTH = 720
const HEIGHT = 520

const NODES: GraphNode[] = [
  { id: 'book:01', kind: 'book', label: '甲书', degree: 3 },
  { id: 'book:02', kind: 'book', label: '乙书', degree: 2 },
  { id: 'book:03', kind: 'book', label: '丙书', degree: 1 },
  { id: 'theme:谋略', kind: 'theme', label: '谋略', degree: 2 },
  { id: 'theme:修心', kind: 'theme', label: '修心', degree: 2 },
  { id: 'chapter:01:00', kind: 'chapter', label: '导言', degree: 1 },
  { id: 'chapter:01:01', kind: 'chapter', label: '第一章', degree: 1 },
]

const EDGES: GraphEdge[] = [
  { source: 'book:01', target: 'theme:谋略', kind: 'theme', label: '以退为进', weight: 2 },
  { source: 'book:02', target: 'theme:谋略', kind: 'theme', label: '守拙', weight: 1 },
  { source: 'book:01', target: 'theme:修心', kind: 'theme', label: '少私寡欲', weight: 1 },
  { source: 'book:03', target: 'theme:修心', kind: 'theme', label: '静', weight: 1 },
  { source: 'book:01', target: 'book:02', kind: 'cross', label: '两书同源。', weight: 1 },
  { source: 'book:01', target: 'chapter:01:00', kind: 'part', label: '', weight: 1 },
  { source: 'book:01', target: 'chapter:01:01', kind: 'part', label: '', weight: 1 },
]

const layout = () => layoutGraph(NODES, EDGES, { width: WIDTH, height: HEIGHT })

describe('layoutGraph', () => {
  it('给每个节点一个坐标', () => {
    const points = layout()
    expect(points.size).toBe(NODES.length)
    for (const node of NODES) expect(points.has(node.id)).toBe(true)
  })

  it('同一张图算两次结果完全一致', () => {
    const first = layout()
    const second = layout()
    for (const node of NODES) {
      expect(second.get(node.id)).toEqual(first.get(node.id))
    }
  })

  it('坐标全部落在画布内', () => {
    for (const point of layout().values()) {
      expect(Number.isFinite(point.x)).toBe(true)
      expect(Number.isFinite(point.y)).toBe(true)
      expect(point.x).toBeGreaterThanOrEqual(0)
      expect(point.x).toBeLessThanOrEqual(WIDTH)
      expect(point.y).toBeGreaterThanOrEqual(0)
      expect(point.y).toBeLessThanOrEqual(HEIGHT)
    }
  })

  it('节点不会全部挤在一个点上', () => {
    const points = [...layout().values()]
    const distinct = new Set(points.map(p => `${Math.round(p.x)},${Math.round(p.y)}`))
    expect(distinct.size).toBeGreaterThan(NODES.length / 2)
  })

  it('空图返回空表，不抛异常', () => {
    expect(layoutGraph([], [], { width: WIDTH, height: HEIGHT }).size).toBe(0)
  })

  it('只有一个节点时把它放在画布中心', () => {
    const only: GraphNode[] = [{ id: 'book:01', kind: 'book', label: '甲书', degree: 0 }]
    const point = layoutGraph(only, [], { width: WIDTH, height: HEIGHT }).get('book:01')!
    expect(point.x).toBeCloseTo(WIDTH / 2, 0)
    expect(point.y).toBeCloseTo(HEIGHT / 2, 0)
  })

  it('边的两端若不在节点表里就忽略它', () => {
    const dangling: GraphEdge[] = [
      { source: 'book:01', target: 'book:99', kind: 'cross', label: '', weight: 1 },
    ]
    expect(() =>
      layoutGraph(NODES, dangling, { width: WIDTH, height: HEIGHT }),
    ).not.toThrow()
  })

  it('章节不会与自己的书重叠成一个点', () => {
    const points = layout()
    const book = points.get('book:01')!
    for (const id of ['chapter:01:00', 'chapter:01:01']) {
      const chapter = points.get(id)!
      expect(Math.hypot(chapter.x - book.x, chapter.y - book.y)).toBeGreaterThan(1)
    }
  })
})

describe('hashUnit', () => {
  it('同一个 id 永远得到同一个值', () => {
    expect(hashUnit('book:08')).toBe(hashUnit('book:08'))
  })

  it('落在 [0, 1) 内', () => {
    for (const node of NODES) {
      const value = hashUnit(node.id)
      expect(value).toBeGreaterThanOrEqual(0)
      expect(value).toBeLessThan(1)
    }
  })

  it('不同 id 给出不同值（用于错开初始角度）', () => {
    expect(hashUnit('book:01')).not.toBe(hashUnit('book:02'))
  })
})

describe('nodeRadius', () => {
  it('度数越高半径越大', () => {
    const low = nodeRadius({ id: 'a', kind: 'book', label: 'a', degree: 1 })
    const high = nodeRadius({ id: 'b', kind: 'book', label: 'b', degree: 16 })
    expect(high).toBeGreaterThan(low)
  })

  it('长的不是线性的：度数差 16 倍，半径不该差 16 倍', () => {
    const low = nodeRadius({ id: 'a', kind: 'book', label: 'a', degree: 1 })
    const high = nodeRadius({ id: 'b', kind: 'book', label: 'b', degree: 16 })
    expect(high / low).toBeLessThan(4)
  })

  it('度数为 0 也画得出来', () => {
    expect(nodeRadius({ id: 'a', kind: 'book', label: 'a', degree: 0 })).toBeGreaterThan(0)
  })

  it('章节比书小', () => {
    const chapter = nodeRadius({ id: 'a', kind: 'chapter', label: 'a', degree: 2 })
    const book = nodeRadius({ id: 'b', kind: 'book', label: 'b', degree: 2 })
    expect(chapter).toBeLessThan(book)
  })
})

describe('neighbourhood', () => {
  it('没有焦点时是空的', () => {
    const result = neighbourhood(EDGES, null)
    expect(result.nodes.size).toBe(0)
    expect(result.edges.size).toBe(0)
  })

  it('只收与焦点相连的节点与边', () => {
    const result = neighbourhood(EDGES, 'theme:谋略')
    expect(result.nodes).toEqual(new Set(['theme:谋略', 'book:01', 'book:02']))
    expect(result.edges.size).toBe(2)
    expect(result.edges.has(edgeKey(EDGES[0]))).toBe(true)
    expect(result.edges.has(edgeKey(EDGES[4]))).toBe(false)
  })

  it('焦点自己总在集合里', () => {
    expect(neighbourhood([], 'book:01').nodes).toEqual(new Set(['book:01']))
  })
})

describe('edgeKey', () => {
  it('区分方向与类型', () => {
    const a: GraphEdge = { source: 'a', target: 'b', kind: 'cross', label: '', weight: 1 }
    const b: GraphEdge = { source: 'b', target: 'a', kind: 'cross', label: '', weight: 1 }
    const c: GraphEdge = { source: 'a', target: 'b', kind: 'theme', label: '', weight: 1 }
    expect(edgeKey(a)).not.toBe(edgeKey(b))
    expect(edgeKey(a)).not.toBe(edgeKey(c))
  })
})

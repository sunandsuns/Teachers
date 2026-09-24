import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type KbGraph, type KbNode, type KbNodeDetail } from '../../api/client'
import { useAsync } from '../../hooks/useAsync'
import { layoutGraph, neighbourhood } from '../../lib/graph'
import { VIEW_H, VIEW_W, applyScope, type Scope } from './constants'

/**
 * 知识库的状态与取数。**这一块里唯一碰 `api.*` 的地方。**
 *
 * 图上同时存在**两份图**，这是这一页最容易搞错的地方：
 *
 *   fullGraph  全图。进页面取一次，随"展开章节"开关重取。
 *   localGraph 聚焦某节点后的局部图（只有它的邻居）。
 *
 * 焦点为空时用全图，有焦点时用局部图——`base` 这一行就是全部逻辑。
 * 把两份图混成一个 state 的话，"再点一次回到全图"就得靠重新请求，
 * 而重新请求会闪一下白。
 *
 * 布局（`layoutGraph`）与高亮（`neighbourhood`）都是纯函数、都只依赖可见图，
 * 所以放在 `useMemo` 里算，不占渲染路径之外的地方。
 */
export function useKnowledgeGraph() {
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
    return layoutGraph(visible.nodes, visible.edges, { width: VIEW_W, height: VIEW_H })
  }, [visible])

  /** 高亮的依据：优先看鼠标悬停，其次看当前焦点。 */
  const highlight = useMemo(() => {
    if (!visible) return { nodes: new Set<string>(), edges: new Set<string>() }
    return neighbourhood(visible.edges, hover ?? focus)
  }, [visible, hover, focus])

  const selectNode = useCallback((nodeId: string) => {
    // 再点一次同一个节点 = 回到全图。比另加一个"取消"按钮好在
    // 手上不用挪位置，这也是 Obsidian 里点空白处的等价操作
    setFocus(current => (current === nodeId ? null : nodeId))
    setHover(null)
  }, [])

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

  const focusedNode = detail?.node ?? visible?.nodes.find(n => n.id === focus) ?? null

  return {
    scope,
    setScope,
    chapters,
    toggleChapters: () => setChapters(value => !value),
    focus,
    setFocus,
    hover,
    setHover,
    selectNode,
    openNode,
    fullGraph,
    fullError,
    loading,
    detail,
    focusFailed,
    focusLoading,
    visible,
    positions,
    highlight,
    focusedNode,
    /** 节点标签要不要全画出来。章节有几百个，全画会糊成一团黑。 */
    labelled: (visible?.nodes.length ?? 0) <= 60,
  }
}

import { useLayoutEffect, useRef, useState } from 'react'
import type { Lang } from '../../i18n'
import type { Avatar } from '../../api/client'
import {
  ANCHOR_BOTTOM,
  ANCHOR_TOP,
  FIGURE_INSET,
  LINES_MIN_WIDTH,
  type Columns,
  type LeadLine,
  type Side,
} from './constants'

/**
 * 牵引线：从画心牵到两侧的分类卡片。
 *
 * 为什么必须**渲染之后**量：线的起点在画框边缘、终点在卡片侧边，两者都由
 * 布局决定——文案长度、语言、图片比例、窗口宽度都会改变它们。任何"算出来"
 * 的坐标都会在某一档屏宽下错位。
 *
 * 三条纪律：
 *   · 用 `useLayoutEffect` 而不是 `useEffect`：要在浏览器绘制**之前**把线放好，
 *     否则会看到线从上一个位置"跳"过来。
 *   · 量不出尺寸（窄屏、或 jsdom 里全是 0）就**不画**。横穿文字的噪线比没有线糟。
 *   · `ResizeObserver` 观察舞台，容器一变就重量；jsdom 没有它，退回 window.resize。
 */
export function useLeadLines(columns: Columns, lang: Lang, avatar: Avatar) {
  const stageRef = useRef<HTMLDivElement>(null)
  const figureRef = useRef<HTMLDivElement>(null)
  const columnRefs = useRef<Record<Side, HTMLDivElement | null>>({ left: null, right: null })
  const cardRefs = useRef<Record<string, HTMLElement | null>>({})
  const [lines, setLines] = useState<LeadLine[]>([])

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
          const endX = side === 'left' ? box.right - stageBox.left : box.left - stageBox.left
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
  }, [columns, lang, avatar])

  return { stageRef, figureRef, columnRefs, cardRefs, lines }
}

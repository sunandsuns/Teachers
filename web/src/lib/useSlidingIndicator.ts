import { useCallback, useEffect, useRef, useState } from 'react'

export interface IndicatorRect {
  left: number
  width: number
}

/**
 * 滑动指示器：让一个背景块在若干等位元素之间"滑"过去，而不是各自亮灭。
 *
 * 这是 Linear / Vercel 那类界面里最容易被记住的一处细节——导航高亮不是
 * 瞬间切换，而是有一块底在移动。观感差别很大：亮灭是"切换"，移动是"我到了那儿"。
 *
 * 实现上必须**量真实几何**：选项宽度不等（"书架"和"知识库"差一倍），
 * 用百分比或固定宽度都会错位。所以：
 *   · 给容器加 ref，给当前激活项加 `data-indicator`；
 *   · 用 `getBoundingClientRect` 量出它的左偏移与宽度（相对容器）；
 *   · 结果交给一个绝对定位的块，用 transform 平移过去。
 *
 * 只在三种时机量：激活项变了、容器尺寸变了、字体加载完。**不参与逐帧计算**，
 * 所以不占主线程——移动本身仍由 CSS transition 在合成层完成。
 *
 * 返回的 `rect` 为 null 时（首帧、量不到）调用方应把指示块设为透明，
 * 避免它从 (0,0) 滑过来那一下的"野跳"。
 */
export function useSlidingIndicator(deps: unknown[] = []) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [rect, setRect] = useState<IndicatorRect | null>(null)

  const measure = useCallback(() => {
    const container = containerRef.current
    if (!container) return
    const active = container.querySelector<HTMLElement>('[data-indicator-active="true"]')
    if (!active) {
      setRect(null)
      return
    }
    const base = container.getBoundingClientRect()
    const box = active.getBoundingClientRect()
    // 宽度为 0 说明这一帧还没布局（例如容器刚挂载），量出来的东西没意义
    if (box.width === 0) return
    // 绝对定位的子元素以**内边距盒**为原点，而 rect 是从**边框盒**算起的，
    // 差了一个左边框的宽度。带描边的容器（Segmented）不扣掉这 1px 就会整体偏一格。
    setRect({ left: box.left - base.left - container.clientLeft, width: box.width })
  }, [])

  useEffect(() => {
    measure()
    // 字体晚于首帧到位时，文字宽度会变，指示块得跟着挪
    if (typeof document !== 'undefined' && 'fonts' in document) {
      void document.fonts.ready.then(measure).catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [measure, ...deps])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }
    const observer = new ResizeObserver(measure)
    observer.observe(container)
    return () => observer.disconnect()
  }, [measure])

  return { containerRef, rect }
}

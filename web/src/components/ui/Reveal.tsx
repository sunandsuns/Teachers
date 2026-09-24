import type { ReactNode } from 'react'
import { delayStyle } from '../../lib/motion'
import { useInView } from '../../lib/useInView'

interface RevealProps {
  children: ReactNode
  /** 在兄弟序列里的位置，用来错峰。同一批里的第 0、1、2… 个依次晚 45ms。 */
  index?: number
  /** 错峰步长（毫秒）。卡片密的地方可以调小。 */
  step?: number
  className?: string
}

/**
 * 滚到才入场。
 *
 * 与"挂载即入场"的区别：长列表里，屏幕外的元素挂载时就开始演，等用户滚到
 * 那儿动画早演完了——等于白做。这个组件先等元素接近视口，再放动画。
 *
 * 落地时用 `animate-rise`（位移 + 微缩放 + expo-out 缓动），比纯淡入多一层
 * "翻到这一页"的实感。
 *
 * 无障碍：`prefers-reduced-motion` 由 index.css 的全局守卫统一压掉，
 * 这里不必再判断一次——一处守卫胜过每个组件各判一遍。
 */
export default function Reveal({ children, index = 0, step = 45, className = '' }: RevealProps) {
  const [ref, inView] = useInView<HTMLDivElement>()

  return (
    <div
      ref={ref}
      className={`${inView ? 'animate-rise' : 'opacity-0'} ${className}`}
      style={inView ? delayStyle(index, step) : undefined}
    >
      {children}
    </div>
  )
}

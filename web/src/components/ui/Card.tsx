import type { HTMLAttributes, ReactNode } from 'react'

/**
 * 表面（surface）——纸感层次的唯一入口。
 *
 * 之前这段 className 在十几处逐字复制（`card p-5`、`card px-5 py-4`…），
 * 改一次阴影要改一片。现在"是什么表面"由一个具名变体决定，各页只负责
 * **留多少白**（padding），不再负责**长什么样**。
 *
 * `SURFACE` 额外导出类名，是给那些必须用别的元素承载的场合——
 * 书目卡片本质是个 `<Link>`，不能塞进 `<div>` 里。这时取类名即可，
 * 比给 Card 加一层 `as` 泛型（TS 里要写一堆 `ElementType` 体操）更划算。
 */
export const SURFACE = {
  /** 静置：卡片、结果条目 */
  flat: 'card',
  /** 可点：悬停抬一档、描边转朱砂 */
  interactive: 'card-interactive',
  /** 大面板：比卡片更沉，用来包住别的卡片 */
  panel: 'panel',
} as const

export type SurfaceVariant = keyof typeof SURFACE

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: SurfaceVariant
  children?: ReactNode
}

export default function Card({
  variant = 'flat',
  className = '',
  children,
  ...rest
}: CardProps) {
  return (
    <div className={`${SURFACE[variant]} ${className}`} {...rest}>
      {children}
    </div>
  )
}

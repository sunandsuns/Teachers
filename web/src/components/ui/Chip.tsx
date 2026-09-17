import type { ButtonHTMLAttributes } from 'react'

interface ChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** 选中态：朱砂实底 */
  active?: boolean
  /** 右侧计数。示例词这类不需要计数的场景就不传 */
  count?: number
}

/**
 * 筛选药丸。书架的类目筛选、感悟的主题筛选、寻章的示例词共用同一种形态——
 * 原来这段 className 在四个地方逐字复制，改一次颜色要改四处。
 */
export default function Chip({ active = false, count, className = '', children, ...rest }: ChipProps) {
  return (
    <button
      type="button"
      className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm transition-colors ${
        active
          ? 'border-cinnabar-500 bg-cinnabar-500 font-medium text-paper-50 shadow-card'
          : 'border-paper-300 bg-paper-50 text-ink-600 hover:border-cinnabar-300 hover:text-cinnabar-600'
      } ${className}`}
      {...rest}
    >
      {children}
      {count !== undefined && (
        <span className={active ? 'text-paper-100/85' : 'text-ink-400'}>{count}</span>
      )}
    </button>
  )
}

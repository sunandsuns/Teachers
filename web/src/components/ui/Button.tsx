import type { ButtonHTMLAttributes } from 'react'
import Spinner from './Spinner'

type Variant = 'primary' | 'secondary' | 'ghost'
type Size = 'sm' | 'md'

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-cinnabar-500 text-paper-50 shadow-card hover:bg-cinnabar-600 active:bg-cinnabar-700',
  secondary:
    'border border-paper-300 bg-paper-50 text-ink-700 hover:border-cinnabar-300 hover:text-cinnabar-600',
  ghost: 'text-ink-600 hover:bg-paper-200 hover:text-ink-800',
}

const SIZES: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-sm',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  /** 在飞：换成转圈并禁用。**只加一个 aria-hidden 的图形**，
   *  按钮的可访问名不变（否则读屏会念成"求教 转圈"）。 */
  loading?: boolean
}

/**
 * 基础按钮。只有三个变体和两个尺寸——用不到的组合就不提供，
 * 免得每个调用点都要先想"该用哪个"。
 *
 * 动效只做两件小事，但决定手感：
 *   · 按下时缩到 0.97——给手指一个"确实按到了"的回执；
 *   · 颜色/阴影走 quick + swift，位移走 CSS transition 而非动画。
 * 全程只碰 transform 与颜色，不触发布局，所以列表里几十个按钮也不掉帧。
 */
export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  className = '',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-[background-color,border-color,color,box-shadow,transform] duration-quick ease-swift active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    >
      {loading && <Spinner size="sm" />}
      {children}
    </button>
  )
}

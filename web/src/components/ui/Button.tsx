import type { ButtonHTMLAttributes } from 'react'

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
}

/**
 * 基础按钮。只有三个变体和两个尺寸——用不到的组合就不提供，
 * 免得每个调用点都要先想"该用哪个"。
 */
export default function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    />
  )
}

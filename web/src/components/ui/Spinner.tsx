/**
 * 转圈。三种尺寸对应三个语境：按钮里、行内提示、整页等待。
 *
 * 一律 aria-hidden：它旁边永远有一句文案（"正在翻阅经典…"），读屏该念的是
 * 那句话，而不是"一个图形"。没有文案的场合由调用方补 `role="status"`。
 */
const SIZES = {
  sm: 'h-3.5 w-3.5 border-2',
  md: 'h-5 w-5 border-2',
  lg: 'h-8 w-8 border-[3px]',
} as const

export default function Spinner({
  size = 'md',
  className = '',
}: {
  size?: keyof typeof SIZES
  className?: string
}) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block shrink-0 animate-spin rounded-full border-paper-300 border-t-cinnabar-500 ${SIZES[size]} ${className}`}
    />
  )
}

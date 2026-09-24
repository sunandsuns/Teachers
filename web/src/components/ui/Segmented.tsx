import { useSlidingIndicator } from '../../lib/useSlidingIndicator'

interface Option<T extends string> {
  value: T
  label: string
}

interface SegmentedProps<T extends string> {
  value: T
  options: readonly Option<T>[]
  onChange: (value: T) => void
  /** 这组开关管的是什么。读屏软件只会念出各按钮的字面，
   *  不给组名就听不出"这几个按钮是一伙的、在切什么"。 */
  ariaLabel?: string
  className?: string
}

/**
 * 分段切换。Reader 的「理解笔记 / 原典全文」与寻章的「全部 / 深读笔记 / 原典全文」
 * 用的是同一种控件，原来各写了一份。
 *
 * 用 aria-pressed 而不是 role="tab"：这组按钮是并列的互斥开关，
 * 不是真正控制面板切换的 tab（没有 tabpanel 关联），标成 tab 反而误导读屏软件。
 *
 * 选中态由一个**会滑动的底块**表达，而不是各按钮自己亮灭。选项宽度不等
 * （"原典全文"比"全部"宽一倍），所以底块的位置与宽度只能实测——
 * 见 `useSlidingIndicator`。实测结果喂给 transform，滑动本身仍由 CSS 在
 * 合成层完成，不占主线程。
 */
export default function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className = '',
}: SegmentedProps<T>) {
  const { containerRef, rect } = useSlidingIndicator([value, options.length])

  return (
    <div
      ref={containerRef}
      role="group"
      aria-label={ariaLabel}
      className={`relative inline-flex rounded-lg border border-paper-300 bg-paper-200/60 p-0.5 ${className}`}
    >
      {/* 首帧量不到位置时（rect 为 null）保持透明，否则它会从左上角"野跳"过来 */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0.5 left-0 rounded-md bg-paper-50 shadow-card transition-[transform,width,opacity] duration-calm ease-spring"
        style={{
          transform: `translateX(${rect?.left ?? 0}px)`,
          width: rect?.width ?? 0,
          opacity: rect ? 1 : 0,
        }}
      />
      {options.map(option => {
        const selected = value === option.value
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            data-indicator-active={selected || undefined}
            onClick={() => onChange(option.value)}
            className={`relative z-10 rounded-md px-3 py-1.5 text-sm font-medium transition-colors duration-quick ${
              selected ? 'text-ink-900' : 'text-ink-500 hover:text-ink-800'
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

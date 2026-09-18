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
 */
export default function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className = '',
}: SegmentedProps<T>) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={`inline-flex rounded-lg border border-paper-300 bg-paper-200/60 p-0.5 ${className}`}
    >
      {options.map(option => {
        const selected = value === option.value
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(option.value)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              selected
                ? 'bg-paper-50 text-ink-900 shadow-card'
                : 'text-ink-500 hover:text-ink-800'
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

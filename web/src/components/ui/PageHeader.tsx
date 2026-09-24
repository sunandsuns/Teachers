import type { ReactNode } from 'react'

/**
 * 页面标题区。五个页面原本各写一份 h1 + 说明文字的间距，
 * 字号一致但下边距在 mb-1/mb-4/mb-5/mb-6 之间摇摆。
 *
 * 三个槽位：`eyebrow`（标题上方的小字，用来标"这一页属于哪一组"）、
 * `title` + `description`、`children`（右侧操作区）。
 *
 * 标题用 `text-balance`：中文标题短，但英文界面下
 * "Knowledge base" 这类词会在窄屏断成难看的两行，交给浏览器均衡断行更稳。
 */
export default function PageHeader({
  eyebrow,
  title,
  description,
  children,
}: {
  /** 标题上方的分组标签。不传就不渲染那一行。 */
  eyebrow?: ReactNode
  title: string
  description?: string
  children?: ReactNode
}) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-1.5 text-xs font-medium uppercase tracking-[0.14em] text-ink-400">
            {eyebrow}
          </div>
        )}
        <h1 className="text-balance font-serif text-2xl font-bold tracking-tight text-ink-900">
          {title}
        </h1>
        {description && <p className="mt-1.5 text-sm text-ink-500">{description}</p>}
      </div>
      {children && <div className="flex shrink-0 items-center gap-2">{children}</div>}
    </div>
  )
}

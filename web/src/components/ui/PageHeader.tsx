import type { ReactNode } from 'react'

/**
 * 页面标题区。五个页面原本各写一份 h1 + 说明文字的间距，
 * 字号一致但下边距在 mb-1/mb-4/mb-5/mb-6 之间摇摆。
 */
export default function PageHeader({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <h1 className="font-serif text-2xl font-bold tracking-tight text-ink-900">{title}</h1>
        {description && <p className="mt-1.5 text-sm text-ink-500">{description}</p>}
      </div>
      {children && <div className="flex shrink-0 items-center gap-2">{children}</div>}
    </div>
  )
}

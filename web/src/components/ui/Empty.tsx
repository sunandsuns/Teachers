import type { ReactNode } from 'react'

interface EmptyProps {
  /** 一句话说明"这里为什么是空的"。必填——空态最忌只有一张图没有解释。 */
  title: ReactNode
  /** 补充说明：怎么才能让它不空。 */
  hint?: ReactNode
  /** 装饰图标。会被标成 aria-hidden，读屏只念文案。 */
  icon?: ReactNode
  /** 下一步的入口（按钮 / 链接）。空态给一个出口，比干瞪眼强。 */
  action?: ReactNode
  className?: string
}

/**
 * 空态。
 *
 * 三个部分各有分工：**标题**回答"发生了什么"，**提示**回答"怎么办"，
 * **出口**让用户能立刻行动。三者都可选，但标题必填——一个没有文字的空态
 * 在无障碍上等于不存在。
 *
 * 垂直留白给得很足（py-16）：空态是页面唯一的内容，挤在顶部会显得页面塌了。
 */
export default function Empty({ title, hint, icon, action, className = '' }: EmptyProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center px-6 py-16 text-center ${className}`}
    >
      {icon && (
        <div
          aria-hidden="true"
          className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-paper-200/70 text-ink-400"
        >
          {icon}
        </div>
      )}
      <p className="font-serif text-base text-ink-500">{title}</p>
      {hint && <p className="mt-2 max-w-sm text-sm leading-relaxed text-ink-400">{hint}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

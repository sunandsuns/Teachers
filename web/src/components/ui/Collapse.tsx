import type { ReactNode } from 'react'

/**
 * 展开容器：内容从 0 高度长到实际高度。
 *
 * 高度由内容决定、算不出来，所以动画交给 `.unfold`（`grid-template-rows`
 * 从 `0fr` 到 `1fr`，浏览器自己插值），见 `index.css`。
 *
 * **只在挂载时演一遍**：调用方用条件渲染决定它存不存在，因此不存在"收起动画
 * 演到一半元素已经没了"的问题。收起比展开少一次动效，是刻意换来的简单——
 * 要做双向动画得引入"卸载前等待"的状态机，不值当。
 */
export default function Collapse({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`unfold ${className}`}>
      <div>{children}</div>
    </div>
  )
}

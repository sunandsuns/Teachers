import Button from './Button'

interface ConfirmBarProps {
  /** 要问用户的那句话。数量、后果都写在里面 */
  message: string
  /** 确认按钮的字。默认交给调用方传，这里只兜一个通用词 */
  confirmLabel: string
  /** 在飞时替换确认按钮的字（"正在删除…"），让等待有反馈 */
  busyLabel?: string
  cancelLabel: string
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/**
 * 就地确认条——替代 `window.confirm`。
 *
 * 为什么不用原生弹窗：删记录这类操作往往发生在嵌进别的界面的页面里
 * （应用自身的预览面板、沙箱 iframe），这种环境会**把 modal 静默拦掉**，
 * `confirm()` 直接返回 false。表现是"点了删除按钮，一点反应都没有"——
 * 既不报错也不提示，用户只能反复点。自己画一条就绕开了这层不确定性，
 * 顺带还能跟纸感配色对齐。
 *
 * 纯展示：状态由调用方持有。这里不做"点外面关掉"之类的花活，
 * 涉及删除的询问就该逼用户明确选一次。
 */
export default function ConfirmBar({
  message,
  confirmLabel,
  busyLabel,
  cancelLabel,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmBarProps) {
  return (
    <div
      role="alertdialog"
      aria-label={message}
      className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-sm bg-cinnabar-50 px-4 py-2.5 ring-1 ring-cinnabar-200 animate-fade-up"
    >
      <span className="min-w-0 text-sm leading-relaxed text-ink-700">{message}</span>
      <span className="ml-auto flex shrink-0 items-center gap-1">
        <Button variant="ghost" size="sm" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </Button>
        <Button variant="primary" size="sm" onClick={onConfirm} disabled={busy}>
          {busy && busyLabel ? busyLabel : confirmLabel}
        </Button>
      </span>
    </div>
  )
}

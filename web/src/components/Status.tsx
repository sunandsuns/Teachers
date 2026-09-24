import type { ReactNode } from 'react'
import { useI18n } from '../i18n'
import EmptyPrimitive from './ui/Empty'
import Spinner from './ui/Spinner'

/**
 * 三态（载入 / 出错 / 空）的统一出口。
 *
 * 这一层是**兼容层**：它把 ui/ 里的原子包成项目里沿用了很久的那套名字
 * （`Loading` / `ErrorBox` / `Empty`），九个页面都在用。这样重做原子层
 * 不必同时改九处调用点，也让"要不要换"变成一个可以分页决定的事。
 *
 * 新写的页面建议直接用 `components/ui` 里的原子，那里能传图标、提示与出口。
 */

/** 载入态：转圈 + 文案。原来只有一段 animate-pulse 文字，看不出"在加载"还是"卡住了"。 */
export function Loading({ text }: { text?: string }) {
  const { t } = useI18n()
  return (
    <div
      role="status"
      className="flex flex-col items-center justify-center gap-3 py-20 text-ink-500"
    >
      <Spinner />
      <span className="text-sm">{text ?? t('status.loading')}</span>
    </div>
  )
}

/** 错误提示：用浅朱砂底而不是 5% 透明度的实色叠加，后者在宣纸底色上几乎看不出来。 */
export function ErrorBox({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="my-6 flex items-start gap-2.5 rounded-lg border border-cinnabar-200 bg-cinnabar-50 px-4 py-3 animate-fade-in"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        fill="currentColor"
        className="mt-0.5 h-4 w-4 shrink-0 text-cinnabar-500"
      >
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zm0-13a1 1 0 011 1v4a1 1 0 11-2 0V6a1 1 0 011-1zm0 9a1.25 1.25 0 100-2.5A1.25 1.25 0 0010 14z"
          clipRule="evenodd"
        />
      </svg>
      <p className="text-sm text-cinnabar-700">{message}</p>
    </div>
  )
}

/** 空态。只收一段话的简化版；要图标、提示与出口请直接用 `ui/Empty`。 */
export function Empty({ children }: { children: ReactNode }) {
  return <EmptyPrimitive title={children} />
}

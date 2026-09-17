import type { ReactNode } from 'react'

/** 载入态：转圈 + 文案。原来只有一段 animate-pulse 文字，看不出"在加载"还是"卡住了"。 */
export function Loading({ text = '加载中…' }: { text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-ink-500">
      <span
        aria-hidden="true"
        className="h-5 w-5 animate-spin rounded-full border-2 border-paper-300 border-t-cinnabar-500"
      />
      <span className="text-sm">{text}</span>
    </div>
  )
}

/** 错误提示：用浅朱砂底而不是 5% 透明度的实色叠加，后者在宣纸底色上几乎看不出来。 */
export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="my-6 flex items-start gap-2.5 rounded-lg border border-cinnabar-200 bg-cinnabar-50 px-4 py-3 animate-fade-in">
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

/** 空态。 */
export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <p className="font-serif text-base text-ink-500">{children}</p>
    </div>
  )
}

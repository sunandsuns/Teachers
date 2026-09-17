import type { ReactNode } from 'react'

type Tone = 'brand' | 'ink' | 'neutral' | 'celadon'

const TONES: Record<Tone, string> = {
  brand: 'bg-cinnabar-100 text-cinnabar-700',
  ink: 'bg-ink-800 text-paper-50',
  neutral: 'bg-paper-200 text-ink-600',
  celadon: 'bg-celadon-100 text-celadon-700',
}

/** 小标记。用于检索结果的「原典 / 笔记」这类一眼可辨的短标签。 */
export default function Badge({
  tone = 'neutral',
  className = '',
  children,
}: {
  tone?: Tone
  className?: string
  children: ReactNode
}) {
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  )
}

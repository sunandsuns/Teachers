import { useEffect, useRef, type KeyboardEvent } from 'react'
import Button from '../../components/ui/Button'
import { useI18n } from '../../i18n'

/** 问题长度上限。更长也不是不行，只是检索质量会跟着掉，不如引导用户把话收一收。 */
const MAX_QUESTION_LENGTH = 500

interface ComposerProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  busy: boolean
}

/**
 * 输入栏。粘在底部（`sticky bottom-4`），滚长对话时始终够得着。
 *
 * 三个细节都不是随手写的：
 *   · **自动长高**：写到第二行时不把字挤在一条里横向滚动。高度只能由内容
 *     算出来（静态类表达不了），所以直接改 DOM 的 `height`，上限交给 `max-h-40`。
 *   · **组词回车放行**：中文输入法里按 Enter 是"选中候选词"，当成发送会把
 *     半截拼音连同正打的字一起发出去。各浏览器对 `isComposing` 的置位时机
 *     不一致，故一并看 `keyCode === 229`（组词期间固定的键码）。
 *   · **焦点环挂在整条栏上**：输入框本身无边框，在它上面画环会很突兀；
 *     挂在外面那层，聚焦时是"整条输入栏亮了"。
 */
export default function Composer({ value, onChange, onSubmit, busy }: ComposerProps) {
  const { t } = useI18n()
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [value])

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey) return
    if (event.nativeEvent.isComposing || event.keyCode === 229) return
    event.preventDefault()
    onSubmit()
  }

  return (
    <form
      onSubmit={e => {
        e.preventDefault()
        onSubmit()
      }}
      className="sticky bottom-4 mt-6"
    >
      {/* items-end：输入框长高后按钮贴着底边，才不会浮在中间 */}
      <div className="card flex items-end gap-2 p-2 pl-4 shadow-composer transition-[border-color,box-shadow] duration-calm focus-within:border-cinnabar-400 focus-within:shadow-glow">
        <textarea
          ref={ref}
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('ask.placeholder')}
          aria-label={t('ask.inputLabel')}
          maxLength={MAX_QUESTION_LENGTH}
          rows={1}
          className="max-h-40 min-w-0 flex-1 resize-none overflow-y-auto bg-transparent py-2 font-serif leading-relaxed text-ink-900 outline-none placeholder:text-ink-400 focus-visible:ring-0"
        />
        <Button type="submit" disabled={busy || !value.trim()} loading={busy}>
          {t('ask.submit')}
        </Button>
      </div>
      <p className="mt-2 text-center text-xs text-ink-400">{t('ask.composerHint')}</p>
    </form>
  )
}

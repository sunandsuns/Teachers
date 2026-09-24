import Markdown from '../../components/Markdown'
import { Spinner } from '../../components/ui'
import { useI18n } from '../../i18n'

/**
 * 「正在想」的两个形态。
 *
 * 分开写是因为它们表达的是**不同的事**：
 *   · `ThinkingBubble` —— 什么都还没回来。给一个转圈，说明"在路上"。
 *   · `StreamingAnswer` —— 云端那条路是流式的，正文已经在往外吐了。
 *     这时候**不能**再用转圈：文字正一个字一个字出现，本身就说明它在动，
 *     旁边再挂一个转圈只会显得界面没反应过来。
 */
export function ThinkingBubble() {
  const { t } = useI18n()
  return (
    <div className="flex justify-start">
      <div className="card flex items-center gap-2.5 px-5 py-3.5">
        <Spinner size="sm" />
        <span className="text-sm text-ink-500">{t('ask.thinking')}</span>
      </div>
    </div>
  )
}

export function StreamingAnswer({ text }: { text: string }) {
  const { t } = useI18n()
  return (
    <div className="card px-5 py-4">
      {text ? (
        <Markdown content={text} />
      ) : (
        <div className="flex items-center gap-2.5">
          <Spinner size="sm" />
          <span className="text-sm text-ink-500">{t('ask.thinking')}</span>
        </div>
      )}
    </div>
  )
}

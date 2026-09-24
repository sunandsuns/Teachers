import Chip from '../../components/ui/Chip'
import { useI18n } from '../../i18n'
import { SUGGESTIONS, suggestionLabel } from './suggestions'

/**
 * 还没提问时的引导卡。
 *
 * 它承担的是"冷启动"——用户第一次进来面对一个空输入框，不知道该问什么、
 * 也不知道问出来会得到什么。给四个具体的处境当例子，比写一段功能介绍有效得多。
 *
 * 卡片在垂直方向居中（由父级的 `justify-center` 决定），否则窄栏顶部一小块、
 * 下面一大片空白，看起来像没加载完。
 *
 * 文件名带 Chips 而不是叫 Suggestions：数据模块叫 `suggestions.ts`，
 * 两者只差大小写的话，在 Windows 上会被 TS 判成同一个模块（TS1261）。
 */
export default function SuggestionChips({
  onPick,
}: {
  onPick: (question: string) => void
}) {
  const { lang, t } = useI18n()

  return (
    <div className="card p-8 text-center">
      <p className="font-serif text-base text-ink-500">{t('ask.suggestionsTitle')}</p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        {SUGGESTIONS.map(s => (
          <Chip key={s.zh} onClick={() => onPick(s.zh)}>
            {suggestionLabel(s, lang)}
          </Chip>
        ))}
      </div>
      <p className="mt-5 text-xs leading-relaxed text-ink-400">{t('ask.suggestionsHint')}</p>
    </div>
  )
}

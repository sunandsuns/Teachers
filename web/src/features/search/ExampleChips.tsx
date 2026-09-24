import { Chip } from '../../components/ui'
import { useI18n } from '../../i18n'
import { EXAMPLES } from './constants'

/**
 * 冷启动引导：还没搜过时摆几个示例词。
 *
 * 示例词**直接触发检索**（而不是只填进输入框）：用户点它图的就是"看看这个例子
 * 能得到什么"，还要再点一次「检索」是白费一步。
 */
export default function ExampleChips({ onPick }: { onPick: (word: string) => void }) {
  const { t } = useI18n()

  return (
    <div className="card p-8 text-center animate-fade-up">
      <p className="font-serif text-base text-ink-500">{t('search.examplesTitle')}</p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        {EXAMPLES.map(word => (
          <Chip key={word} onClick={() => onPick(word)}>
            {word}
          </Chip>
        ))}
      </div>
    </div>
  )
}

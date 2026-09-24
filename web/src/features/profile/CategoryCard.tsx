import type { TraitItem } from '../../api/client'
import { useI18n, traitCategory } from '../../i18n'
import { delayStyle } from '../../lib/motion'
import type { CategoryGroup } from './constants'

/**
 * 一个分类的卡片：标题 + 该分类下的全部特征。
 *
 * 每条特征都带三样东西，缺一样这张卡片就不可信：
 *   · **正文**——它说你是什么样的人
 *   · **依据**——你当时说的原话。画像最怕"它凭什么这么说"，这句话就是答案
 *   · **把握**——模型的置信度。不写出来的话，0.4 和 0.8 的特征看着一样重
 */
export default function CategoryCard({
  group,
  index,
  onDelete,
  cardRef,
}: {
  group: CategoryGroup
  /** 在整页里的位置，用来错峰入场 */
  index: number
  onDelete: (trait: TraitItem) => void
  cardRef: (el: HTMLElement | null) => void
}) {
  const { lang, t } = useI18n()

  return (
    <article
      ref={cardRef}
      className="card animate-fade-up px-4 py-3.5 transition-colors duration-quick ease-swift hover:border-cinnabar-200"
      style={delayStyle(index, 60, 300)}
    >
      <h3 className="font-serif text-sm font-bold tracking-wide text-cinnabar-600">
        {traitCategory(group.category, lang)}
      </h3>

      <ul className="mt-2 space-y-3">
        {group.traits.map(trait => (
          <li key={trait.id}>
            <p className="break-words text-sm leading-relaxed text-ink-800">{trait.content}</p>

            {/* 依据要留着：画像最怕"它凭什么这么说"，这句话就是答案 */}
            {trait.evidence && (
              <p className="mt-1 break-words border-l-2 border-paper-300 pl-2 text-xs leading-relaxed text-ink-400">
                {t('profile.evidence', { text: trait.evidence })}
              </p>
            )}

            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              <span className="tabular-nums text-ink-300">
                {t('profile.confidence', { percent: Math.round(trait.confidence * 100) })}
              </span>
              <button
                type="button"
                onClick={() => onDelete(trait)}
                className="rounded transition-colors duration-quick ease-swift hover:text-cinnabar-600"
              >
                {t('profile.deleteTrait')}
              </button>
            </p>
          </li>
        ))}
      </ul>
    </article>
  )
}

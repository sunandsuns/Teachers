import Chip from '../../components/ui/Chip'
import { categoryName, useI18n } from '../../i18n'

interface CategoryBarProps {
  categories: string[]
  /** 每个类目下的书目数，与 `categories` 同源算出。 */
  counts: Record<string, number>
  total: number
  active: string | null
  onChange: (category: string | null) => void
}

/**
 * 类目筛选条。
 *
 * 计数直接印在药丸上（"历史文献 4"）——不然用户点了才知道里面有几本，
 * 而"这个类目其实是空的"是最该被提前看见的信息。
 *
 * `role="group"` + 组名是给读屏用的：一排药丸若没有组名，
 * 读屏只会念出"全部 15 历史文献 4 哲学 3…"，听不出它们是一组筛选项。
 */
export default function CategoryBar({
  categories,
  counts,
  total,
  active,
  onChange,
}: CategoryBarProps) {
  const { lang, t } = useI18n()

  return (
    <div
      role="group"
      aria-label={t('library.filterLabel')}
      className="mb-6 flex flex-wrap gap-2"
    >
      <Chip active={active === null} onClick={() => onChange(null)} count={total}>
        {t('library.all')}
      </Chip>
      {categories.map(name => (
        <Chip
          key={name}
          active={active === name}
          onClick={() => onChange(name)}
          count={counts[name] ?? 0}
        >
          {categoryName(name, lang)}
        </Chip>
      ))}
    </div>
  )
}

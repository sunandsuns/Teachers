import { categoryName, useI18n } from '../i18n'

/**
 * 类目标记。
 *
 * 原来是"深墨底 + 白字"的实心块，但七个类目里有六个映射到了几乎同一个深墨色，
 * 扫一眼书架分不出类目——徽章等于白占位置。改成中性底色 + 一个色点：
 * 文字负责说清是什么，色点负责让它在列表里可被扫到。
 *
 * 色相避开紫 / 蓝紫 / 靛（那些是生成式 UI 的默认色，也最容易显得廉价）。
 */
const CATEGORY_DOT: Record<string, string> = {
  哲学: 'bg-sky-600',
  处世: 'bg-cinnabar-500',
  术数: 'bg-amber-500',
  // 政治原本给的是 orange-600，和处世的朱砂红在 6px 的圆点上几乎分不出来，
  // 压深成褐橙才能和红色拉开
  政治: 'bg-orange-800',
  兵学: 'bg-ink-800',
  纵横: 'bg-emerald-600',
  历史文献: 'bg-celadon-500',
}

export function categoryDot(category: string): string {
  return CATEGORY_DOT[category] ?? 'bg-ink-400'
}

export default function CategoryTag({ category }: { category: string }) {
  const { lang } = useI18n()
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-paper-300 bg-paper-50 px-2 py-0.5 text-xs text-ink-600">
      <span className={`h-1.5 w-1.5 rounded-full ${categoryDot(category)}`} aria-hidden="true" />
      {/* 色点按原始中文名取色、文字按当前语言显示：语料里叫什么不影响配色，
          换语言也不会让某个类目忽然换颜色 */}
      {categoryName(category, lang)}
    </span>
  )
}

import type { InsightItem } from '../../api/client'
import { useI18n } from '../../i18n'

/**
 * 今日感悟——整页的题眼，所以给它最大的字号与最暖的底色。
 *
 * 两侧的引号是**装饰**（aria-hidden）：读屏软件念出「天行健，君子以自强不息」
 * 时不该夹带两个书名号似的符号。用楷体大字排在角落，比居中放一个引号图标
 * 更像"批注"而不是"卡片模板"。
 */
export default function DailyHighlight({ insight }: { insight: InsightItem }) {
  const { t } = useI18n()

  return (
    <div className="card relative mb-6 overflow-hidden border-cinnabar-200 bg-cinnabar-50 px-6 py-10 text-center sm:px-10 animate-rise">
      {/* 顶部一道细朱砂：给这块"今日"一个起手，避免大色块没有边界 */}
      <span
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cinnabar-300 to-transparent"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute left-4 top-3 select-none font-kai text-6xl leading-none text-cinnabar-200"
      >
        「
      </span>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute bottom-3 right-4 select-none font-kai text-6xl leading-none text-cinnabar-200"
      >
        」
      </span>

      <span className="text-xs tracking-widest text-cinnabar-600">{t('insight.daily')}</span>

      <blockquote className="mx-auto mt-5 max-w-2xl font-kai text-xl leading-relaxed text-balance text-ink-900 sm:text-2xl">
        {insight.text}
      </blockquote>

      <p className="mx-auto mt-5 max-w-xl text-sm leading-relaxed text-ink-600">
        {insight.interpretation}
      </p>

      <p className="mt-5 font-serif text-xs text-ink-400">—— {insight.source}</p>
    </div>
  )
}

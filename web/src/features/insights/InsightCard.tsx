import type { InsightItem } from '../../api/client'
import { Badge } from '../../components/ui'
import { themeName, useI18n } from '../../i18n'

/**
 * 主题结果里的一条感悟。
 *
 * 用 `flex-col` + `mt-auto` 把出处与主题徽章顶到底部：同一行里几张卡片的
 * 引文长短不一，底栏对齐之后，横向扫视时"出处在哪"是固定的，不必逐张找。
 */
export default function InsightCard({ insight }: { insight: InsightItem }) {
  const { lang } = useI18n()

  return (
    <article className="card-interactive flex h-full flex-col p-5">
      <blockquote className="border-l-2 border-cinnabar-400 pl-4 font-kai text-lg leading-relaxed text-ink-900">
        {insight.text}
      </blockquote>
      <p className="mt-3 text-sm leading-relaxed text-ink-600">{insight.interpretation}</p>

      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-4">
        <span className="font-serif text-xs text-ink-400">—— {insight.source}</span>
        <div className="flex flex-wrap gap-1.5">
          {insight.themes.map(theme => (
            <Badge key={theme}>{themeName(theme, lang)}</Badge>
          ))}
        </div>
      </div>
    </article>
  )
}

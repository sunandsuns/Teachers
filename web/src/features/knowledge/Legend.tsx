import { useI18n } from '../../i18n'

/**
 * 图例。
 *
 * 色点用 `bg-*` 而不是 `fill-*`：`fill-*` 是给 SVG 的，落在 `<span>` 上
 * 不产生任何视觉效果——三个色点会集体隐形，图例只剩三个词。
 * （原来就是这样，图上三种节点长得不一样，图例却看不出区别。）
 */
function LegendItem({ className, label }: { className: string; label: string }) {
  return (
    <li className="inline-flex items-center gap-1.5">
      <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${className}`} />
      {label}
    </li>
  )
}

export default function Legend() {
  const { t } = useI18n()

  return (
    <ul className="flex items-center gap-3.5 text-xs text-ink-500">
      <LegendItem className="bg-cinnabar-500" label={t('kb.legend.theme')} />
      <LegendItem className="bg-ink-700" label={t('kb.legend.book')} />
      <LegendItem className="bg-paper-400" label={t('kb.legend.chapter')} />
    </ul>
  )
}

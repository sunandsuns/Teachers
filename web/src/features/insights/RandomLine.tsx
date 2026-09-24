import type { InsightItem } from '../../api/client'
import { Button } from '../../components/ui'
import { useI18n } from '../../i18n'

/**
 * 「随机一则」。
 *
 * 摆在按钮右边而不是下面另起一块：随机一条本来就是"随手翻翻"，
 * 给它一整张卡片会喧宾夺主，压过上面的「今日感悟」。
 *
 * 结果用 `animate-fade-in` + key 触发：每次换一条都会重挂，动画重放一次，
 * 用户能看出"内容真的换了"，而不是怀疑按钮没生效。
 */
export default function RandomLine({
  item,
  onRefresh,
}: {
  item: InsightItem | null
  onRefresh: () => void
}) {
  const { t } = useI18n()

  return (
    <div className="mb-8 flex flex-wrap items-center gap-3">
      <Button variant="secondary" onClick={onRefresh}>
        {t('insight.random')}
      </Button>
      {item && (
        <p
          key={item.id}
          className="min-w-0 flex-1 truncate font-serif text-sm text-ink-600 animate-fade-in"
        >
          「{item.text}」
          <span className="ml-2 whitespace-nowrap text-xs text-ink-400">—— {item.source}</span>
        </p>
      )}
    </div>
  )
}

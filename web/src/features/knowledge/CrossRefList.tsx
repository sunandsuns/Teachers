import type { KbNodeDetail } from '../../api/client'
import { useI18n } from '../../i18n'

/**
 * 「写下的互参」——作者明写的跨书对照。
 *
 * 与主题归属不同，互参是**作者自己写下的**判断，所以这里给的是原文摘句，
 * 界面一个字都不改。对照的是哪一本也一并说清（与《X》），否则一串摘句
 * 会读不出方向。
 */
export default function CrossRefList({ detail }: { detail: KbNodeDetail }) {
  const { t } = useI18n()

  return (
    <div className="card p-4">
      <h3 className="mb-2 text-xs font-medium text-ink-500">{t('kb.crossRefs')}</h3>
      <ul className="space-y-2">
        {detail.cross_refs.map(ref => (
          <li key={ref.name} className="text-xs leading-relaxed text-ink-600">
            <span className="font-serif text-ink-800">与《{ref.name}》</span>：{ref.detail}
          </li>
        ))}
      </ul>
    </div>
  )
}

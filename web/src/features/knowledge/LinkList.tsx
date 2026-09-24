import type { KbLink } from '../../api/client'
import { useI18n } from '../../i18n'
import { EDGE_LABEL_KEY, nodeLabel } from './constants'

/**
 * 双链列表（出链 / 反链）。
 *
 * 两个方向用同一个组件、同一份数据的两种切片：`outgoing` 说"我引了谁"，
 * `backlinks` 说"谁引了我"。**反链为空不是错误**，是这本书还没被别的书写到——
 * 所以空态给的是一句解释（"还没有别的书写到它"），不是一片空白。
 *
 * 每一条右侧标出边的类型（主题归属 / 经典互参 / 章节构成）：同一条链在不同
 * 语境下的分量完全不同，不标的话用户只能点进去才知道。
 */
export default function LinkList({
  title,
  empty,
  links,
  onPick,
  activeId,
  onHover,
}: {
  title: string
  empty: string
  links: KbLink[]
  onPick: (nodeId: string) => void
  activeId: string | null
  onHover: (nodeId: string | null) => void
}) {
  const { lang, t } = useI18n()

  return (
    <div className="card p-4">
      <h3 className="mb-2 flex items-center justify-between text-xs font-medium text-ink-500">
        {title}
        <span className="tabular-nums text-ink-400">{links.length}</span>
      </h3>

      {links.length === 0 ? (
        <p className="text-xs text-ink-400">{empty}</p>
      ) : (
        <ul className="space-y-0.5">
          {links.map(link => (
            <li key={`${link.direction}-${link.kind}-${link.node_id}`}>
              <button
                type="button"
                onClick={() => onPick(link.node_id)}
                onMouseEnter={() => onHover(link.node_id)}
                onMouseLeave={() => onHover(null)}
                className={`w-full rounded-md px-2 py-1.5 text-left transition-colors duration-quick ease-swift ${
                  activeId === link.node_id ? 'bg-paper-200' : 'hover:bg-paper-200'
                }`}
              >
                <span className="flex items-center gap-2">
                  <span className="truncate font-serif text-sm text-ink-800">
                    {nodeLabel(link, lang)}
                  </span>
                  <span className="shrink-0 text-[10px] text-ink-400">
                    {t(EDGE_LABEL_KEY[link.kind as keyof typeof EDGE_LABEL_KEY] ?? 'kb.kind.theme')}
                  </span>
                </span>
                {/* 边上的说明来自语料原文，界面只负责显示，不许自己编一句 */}
                {link.edge_label && (
                  <span className="mt-0.5 line-clamp-2 block text-xs leading-relaxed text-ink-500">
                    {link.edge_label}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

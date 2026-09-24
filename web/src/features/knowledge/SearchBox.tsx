import type { KbNode } from '../../api/client'
import { Button } from '../../components/ui'
import { useI18n } from '../../i18n'
import { nodeLabel } from './constants'
import { useNodeSearch } from './useNodeSearch'

/**
 * 按名字找节点。
 *
 * `role="search"` 落在**整块**上而不是 `<form>` 上：检索结果也属于"搜索区"，
 * 读屏软件跳到这里时该一并看到命中列表。
 */
export default function SearchBox({ onPick }: { onPick: (nodeId: string) => void }) {
  const { lang, t } = useI18n()
  const { query, setQuery, results, failed, searching, submit, clear } = useNodeSearch()

  return (
    <div className="card p-4" role="search">
      <form onSubmit={submit} className="flex items-center gap-2">
        <label htmlFor="kb-search" className="sr-only">
          {t('kb.searchLabel')}
        </label>
        <input
          id="kb-search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder={t('kb.searchPlaceholder')}
          className="field min-w-0 flex-1"
        />
        <Button type="submit" size="sm" variant="secondary" loading={searching}>
          {t('kb.searchSubmit')}
        </Button>
      </form>

      {failed && <p className="mt-2 text-xs text-cinnabar-600">{t('kb.loadFailed')}</p>}

      {results !== null &&
        (results.length === 0 ? (
          <p className="mt-2 text-xs text-ink-400">{t('kb.searchEmpty')}</p>
        ) : (
          <ul className="mt-2 space-y-0.5">
            {results.map((node: KbNode, i) => (
              <li key={node.id} className="animate-fade-up" style={{ animationDelay: `${i * 30}ms` }}>
                <button
                  type="button"
                  onClick={() => {
                    onPick(node.id)
                    clear()
                  }}
                  className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm text-ink-700 transition-colors duration-quick ease-swift hover:bg-paper-200"
                >
                  <span className="truncate">{nodeLabel(node, lang)}</span>
                  <span className="shrink-0 text-xs tabular-nums text-ink-400">
                    {t('kb.meta.degree', { count: node.degree })}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ))}
    </div>
  )
}

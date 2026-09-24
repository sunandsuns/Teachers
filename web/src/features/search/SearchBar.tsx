import type { SearchKind } from '../../api/client'
import { Button, Segmented } from '../../components/ui'
import { useI18n } from '../../i18n'
import { KIND_TABS } from './constants'

/**
 * 检索栏 + 范围切换。
 *
 * 范围切换放在输入框**下面**而不是右边：三个标签加起来不窄，挤在一行会在
 * 窄屏把输入框压成一条缝。分成两行之后，输入框始终是整宽的。
 */
export default function SearchBar({
  query,
  kind,
  searching,
  onQueryChange,
  onSubmit,
  onKindChange,
}: {
  query: string
  kind: SearchKind
  searching: boolean
  onQueryChange: (value: string) => void
  onSubmit: () => void
  onKindChange: (kind: SearchKind) => void
}) {
  const { t } = useI18n()

  return (
    <>
      <form
        onSubmit={event => {
          event.preventDefault()
          onSubmit()
        }}
        className="mb-4 flex flex-col gap-2 sm:flex-row"
      >
        <input
          value={query}
          onChange={event => onQueryChange(event.target.value)}
          placeholder={t('search.placeholder')}
          aria-label={t('search.keywordLabel')}
          className="field min-w-0 flex-1 font-serif"
        />
        <Button
          type="submit"
          disabled={searching || !query.trim()}
          loading={searching}
          className="shrink-0 sm:px-6"
        >
          {t('search.submit')}
        </Button>
      </form>

      <div className="mb-6">
        <Segmented
          value={kind}
          ariaLabel={t('search.scopeGroup')}
          options={KIND_TABS.map(tab => ({ value: tab.value, label: t(tab.key) }))}
          onChange={onKindChange}
        />
      </div>
    </>
  )
}

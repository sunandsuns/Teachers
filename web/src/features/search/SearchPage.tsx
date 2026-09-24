import { useI18n } from '../../i18n'
import { ErrorBox, Loading } from '../../components/Status'
import { PageHeader } from '../../components/ui'
import ExampleChips from './ExampleChips'
import ResultList from './ResultList'
import SearchBar from './SearchBar'
import { useSearch } from './useSearch'

/**
 * 寻章：跨全库检索——既查深读笔记，也查原典全文。
 *
 * 编排层只做三件事：把 hook 的状态摊给子组件、把子组件的回调接回 hook、
 * 决定"此刻该显示哪一块"。任何网络、任何布局细节都不在这里。
 *
 * 页面有且只有**四种**互斥的呈现，顺序即优先级：
 *
 *   1. 出错        → 错误框（压过一切，包括旧结果——留着旧结果只会让人困惑）
 *   2. 检索中      → 转圈（布局未知，所以用 spinner 而不是骨架）
 *   3. 搜过且没命中 → 「没找到，换个词」
 *   4. 搜过且有命中 → 结果列表
 *
 * 都没沾上（results === null）→ 摆示例词。这正是 useSearch 里那个 null 的用处：
 * 它把"还没搜"和"搜了没命中"分开，否则用户一进页面就会看到"没有找到相关段落"。
 */
export default function SearchPage() {
  const { t } = useI18n()
  const { query, setQuery, kind, results, searching, error, run, switchKind } = useSearch()

  return (
    <section>
      <PageHeader title={t('search.title')} description={t('search.description')} />

      <SearchBar
        query={query}
        kind={kind}
        searching={searching}
        onQueryChange={setQuery}
        onSubmit={() => void run(query)}
        onKindChange={switchKind}
      />

      {error && <ErrorBox message={error} />}
      {searching && <Loading text={t('search.searching')} />}

      {/* 还没搜过：给示例词，让人有东西可点 */}
      {results === null && !searching && !error && (
        <ExampleChips
          onPick={word => {
            setQuery(word)
            void run(word)
          }}
        />
      )}

      {/* 搜过了：先报数，再列结果。空结果也算"搜过了" */}
      {results !== null && !searching && !error && (
        <>
          <p className="mb-4 text-sm text-ink-500">
            {results.length ? t('search.hits', { count: results.length }) : t('search.noHits')}
          </p>
          {results.length > 0 && <ResultList results={results} />}
        </>
      )}
    </section>
  )
}

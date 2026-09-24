import { useState } from 'react'
import { api, type SearchKind, type SearchResultItem } from '../../api/client'
import { useI18n } from '../../i18n'
import { RESULT_LIMIT } from './constants'

/**
 * 寻章的状态与检索副作用。**这一块里唯一碰 `api.*` 的地方。**
 *
 * `results === null` 与 `results === []` 是**两件不同的事**，这个区分是这一页的核心：
 *
 *   null  = 还没搜过     → 摆示例词，引导用户开口
 *   []    = 搜了没命中   → 说"没找到，换个词"
 *
 * 合成一个空数组的话，用户一进页面就会看到"没有找到相关段落"——
 * 明明还没搜呢。所以这个 null 必须保住。
 */
export function useSearch() {
  const { t } = useI18n()
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState<SearchKind>('all')
  //: null 表示"还没搜过"，见上面的说明
  const [results, setResults] = useState<SearchResultItem[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(raw: string, nextKind: SearchKind = kind) {
    const keyword = raw.trim()
    if (!keyword || searching) return
    setSearching(true)
    setError(null)
    try {
      const resp = await api.search(keyword, RESULT_LIMIT, nextKind)
      setResults(resp.results)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('search.failed'))
    } finally {
      setSearching(false)
    }
  }

  /** 切范围时**用当前关键词立刻重搜**——否则用户会以为"切了没反应"。
   *  词是空的时候就只换标签，不必白跑一趟。 */
  function switchKind(next: SearchKind) {
    setKind(next)
    if (query.trim()) void run(query, next)
  }

  return { query, setQuery, kind, results, searching, error, run, switchKind }
}

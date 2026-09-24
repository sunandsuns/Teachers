import { useCallback, useState, type FormEvent } from 'react'
import { api, type KbNode } from '../../api/client'

/**
 * 按名字找节点。**知识库里第二处、也是最后一处碰 `api.*` 的地方。**
 *
 * 走的是后端检索而不是在已加载的图上做本地过滤——因为"章节"这类节点
 * 平时并不在图里，本地过滤就找不到了。
 *
 * `results === null`（没搜过）与 `[]`（搜了没命中）必须分开：
 * 前者什么都不显示，后者要说明"没有匹配的节点"。合并的话，搜索框一出现
 * 就会挂着一条"没有匹配"的结论，像是刚搜过一场空。
 */
export function useNodeSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<KbNode[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [searching, setSearching] = useState(false)

  const submit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault()
      setFailed(false)
      setSearching(true)
      try {
        setResults(await api.kbSearch(query))
      } catch {
        // 检索失败只让这一块变红，不把整页炸掉——图还在，用户还能点
        setFailed(true)
      } finally {
        setSearching(false)
      }
    },
    [query],
  )

  /** 选中一条结果之后把搜索区收干净，不然它会一直挂在右侧栏 */
  const clear = useCallback(() => {
    setResults(null)
    setQuery('')
  }, [])

  return { query, setQuery, results, failed, searching, submit, clear }
}

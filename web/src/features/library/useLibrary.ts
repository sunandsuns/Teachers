import { useMemo, useState } from 'react'
import { api } from '../../api/client'
import { useAsync } from '../../hooks/useAsync'

/**
 * 书架的数据与筛选逻辑。
 *
 * 从页面里抽出来，是为了让页面只剩"怎么摆"这件事。这里管的是"摆什么"：
 * 拉数据、算类目、按类目过滤。两件事分开之后，改筛选规则不必碰 JSX，
 * 改版式也不必读筛选代码。
 */
export function useLibrary() {
  const { data: books, error, loading } = useAsync(() => api.listBooks(), [])
  const [category, setCategory] = useState<string | null>(null)

  // 分类顺序按书目顺序首次出现决定，与后端注册表保持一致。
  // 筛选用**原始中文类目**而不是显示名：显示名会随语言变，
  // 拿它当键会让"切换语言"把已选中的筛选条件弄丢。
  const categories = useMemo(() => {
    const seen: string[] = []
    for (const book of books ?? []) {
      if (!seen.includes(book.category)) seen.push(book.category)
    }
    return seen
  }, [books])

  /** 每个类目下有几本。一次遍历算完，避免在 JSX 里对每个药丸各 filter 一遍。 */
  const counts = useMemo(() => {
    const acc: Record<string, number> = {}
    for (const book of books ?? []) {
      acc[book.category] = (acc[book.category] ?? 0) + 1
    }
    return acc
  }, [books])

  const visible = useMemo(
    () => (category ? (books ?? []).filter(book => book.category === category) : books ?? []),
    [books, category],
  )

  return {
    books: books ?? [],
    error,
    loading,
    category,
    setCategory,
    categories,
    counts,
    visible,
  }
}

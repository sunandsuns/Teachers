import { useState } from 'react'
import { api } from '../../api/client'
import { useAsync } from '../../hooks/useAsync'

/**
 * 感悟页的取数与筛选状态。**这一块里唯一碰 `api.*` 的地方。**
 *
 * 四条请求各有各的脾气，所以分别对待：
 *
 *   dailyInsight    一天一条，跟着日期走 → 依赖为空，进页面取一次
 *   randomInsight   语义就是"再给我一条别的" → 依赖 refreshKey，点一次换一次
 *   insightThemes   主题与计数，基本不变 → 依赖为空
 *   insightsByTheme 只有选了主题才发 → 未选时 `Promise.resolve(null)` 短路
 *
 * 最后一条尤其要注意：不短路的话会以 `theme = null` 发一次请求，
 * 后端要么 400、要么返回全量，两种都不是这里想要的。
 */
export function useInsights() {
  const [theme, setTheme] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const { data: daily } = useAsync(() => api.dailyInsight(), [])
  const { data: randomItem } = useAsync(() => api.randomInsight(), [refreshKey])
  const { data: themeData, error, loading } = useAsync(() => api.insightThemes(), [])

  const { data: themeInsights } = useAsync(
    () => (theme ? api.insightsByTheme(theme) : Promise.resolve(null)),
    [theme],
  )

  return {
    theme,
    setTheme,
    daily,
    randomItem,
    themeData,
    themeInsights,
    error,
    loading,
    /** 换一条随机感悟 */
    refresh: () => setRefreshKey(k => k + 1),
  }
}

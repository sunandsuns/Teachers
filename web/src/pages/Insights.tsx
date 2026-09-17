import { useState } from 'react'
import { api, type InsightItem } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { Loading, ErrorBox, Empty } from '../components/Status'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Chip from '../components/ui/Chip'
import PageHeader from '../components/ui/PageHeader'

function InsightCard({ insight }: { insight: InsightItem }) {
  return (
    <article className="card flex flex-col p-5 hover:border-cinnabar-300">
      <blockquote className="border-l-2 border-cinnabar-400 pl-4 font-kai text-lg leading-relaxed text-ink-900">
        {insight.text}
      </blockquote>
      <p className="mt-3 text-sm leading-relaxed text-ink-600">{insight.interpretation}</p>
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-4">
        <span className="font-serif text-xs text-ink-400">—— {insight.source}</span>
        <div className="flex flex-wrap gap-1.5">
          {insight.themes.map(theme => (
            <Badge key={theme}>{theme}</Badge>
          ))}
        </div>
      </div>
    </article>
  )
}

export default function Insights() {
  const [theme, setTheme] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const { data: daily } = useAsync(() => api.dailyInsight(), [])
  const { data: randomItem } = useAsync(() => api.randomInsight(), [refreshKey])
  const { data: themeData, error, loading } = useAsync(() => api.insightThemes(), [])

  const { data: themeInsights } = useAsync(
    () => (theme ? api.insightsByTheme(theme) : Promise.resolve(null)),
    [theme],
  )

  return (
    <section>
      <PageHeader title="感悟" description="每日一句经典智慧，给生活一点提醒" />

      {daily && (
        <div className="card mb-6 border-cinnabar-200 bg-cinnabar-50 px-6 py-10 text-center sm:px-10">
          <span className="text-xs tracking-widest text-cinnabar-600">今日感悟</span>
          <blockquote className="mx-auto mt-5 max-w-2xl font-kai text-xl leading-relaxed text-ink-900 sm:text-2xl">
            {daily.text}
          </blockquote>
          <p className="mx-auto mt-5 max-w-xl text-sm leading-relaxed text-ink-600">
            {daily.interpretation}
          </p>
          <p className="mt-5 font-serif text-xs text-ink-400">—— {daily.source}</p>
        </div>
      )}

      <div className="mb-8 flex flex-wrap items-center gap-3">
        <Button variant="secondary" onClick={() => setRefreshKey(k => k + 1)}>
          随机一则
        </Button>
        {randomItem && (
          <p className="min-w-0 flex-1 truncate font-serif text-sm text-ink-600">
            「{randomItem.text}」
            <span className="ml-2 whitespace-nowrap text-xs text-ink-400">
              —— {randomItem.source}
            </span>
          </p>
        )}
      </div>

      {loading && <Loading />}
      {error && <ErrorBox message={error} />}

      {themeData && (
        <>
          <h2 className="mb-4 font-serif text-lg font-bold text-ink-900">按主题浏览</h2>
          <div className="mb-6 flex flex-wrap gap-2">
            <Chip active={theme === null} onClick={() => setTheme(null)}>
              全部
            </Chip>
            {themeData.themes.map(t => (
              <Chip
                key={t}
                active={theme === t}
                onClick={() => setTheme(t)}
                count={themeData.counts[t]}
              >
                {t}
              </Chip>
            ))}
          </div>
          {/* 未选主题时下方本来是一片空白，补一句引导把动作说清楚 */}
          {theme === null && (
            <p className="text-sm text-ink-400">选择一个主题，看看不同的经典怎么说</p>
          )}
        </>
      )}

      {theme && themeInsights && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {themeInsights.items.length ? (
            themeInsights.items.map(item => <InsightCard key={item.id} insight={item} />)
          ) : (
            <div className="lg:col-span-2">
              <Empty>该主题下暂无感悟</Empty>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

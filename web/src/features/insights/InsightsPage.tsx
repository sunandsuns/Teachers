import { Empty, PageHeader, Reveal } from '../../components/ui'
import { ErrorBox, Loading } from '../../components/Status'
import { useI18n } from '../../i18n'
import DailyHighlight from './DailyHighlight'
import InsightCard from './InsightCard'
import RandomLine from './RandomLine'
import ThemeFilter from './ThemeFilter'
import { useInsights } from './useInsights'

/**
 * 感悟：每日一句 + 按主题翻阅。
 *
 * 编排层只做三件事：把 hook 的状态摊给子组件、把子组件的回调接回 hook、
 * 决定"此刻该显示哪一块"。
 *
 * 版面的次序是有讲究的：**今日感悟 → 随机一则 → 按主题浏览**。
 * 由"一天只看一句"到"随手多翻几条"再到"主动去挖一个主题"，
 * 用户的投入是递进的，界面就该按这个顺序铺开。
 */
export default function InsightsPage() {
  const { t } = useI18n()
  const { theme, setTheme, daily, randomItem, themeData, themeInsights, error, loading, refresh } =
    useInsights()

  return (
    <section>
      <PageHeader title={t('insight.title')} description={t('insight.description')} />

      {daily && <DailyHighlight insight={daily} />}

      <RandomLine item={randomItem} onRefresh={refresh} />

      {loading && <Loading />}
      {error && <ErrorBox message={error} />}

      {themeData && <ThemeFilter themeData={themeData} theme={theme} onPick={setTheme} />}

      {theme && themeInsights && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {themeInsights.items.length ? (
            themeInsights.items.map((item, i) => (
              <Reveal key={item.id} index={i} className="h-full">
                <InsightCard insight={item} />
              </Reveal>
            ))
          ) : (
            <div className="lg:col-span-2">
              <Empty title={t('insight.emptyTheme')} />
            </div>
          )}
        </div>
      )}
    </section>
  )
}

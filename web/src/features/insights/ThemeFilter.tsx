import type { ThemeListResponse } from '../../api/client'
import { Chip, Reveal } from '../../components/ui'
import { themeName, useI18n } from '../../i18n'

/**
 * 主题筛选。
 *
 * 「全部」也是选项之一，且**必须存在**：否则用户选了一个主题之后就没有路回到
 * 全览，只能刷新页面——这是很多筛选器都会犯的错。
 *
 * 计数交给 Chip 的 `count` 槽（渲染成嵌套 span），而不是拼进标签文字里。
 * 拼进去的话，读屏软件念出来是"逆境五"，而且测试也再找不到一个干净的主题名。
 */
export default function ThemeFilter({
  themeData,
  theme,
  onPick,
}: {
  themeData: ThemeListResponse
  theme: string | null
  onPick: (theme: string | null) => void
}) {
  const { lang, t } = useI18n()

  return (
    <>
      <h2 className="mb-4 font-serif text-lg font-bold text-ink-900">{t('insight.byTheme')}</h2>

      <div className="mb-6 flex flex-wrap gap-2">
        <Reveal index={0} step={30}>
          <Chip active={theme === null} onClick={() => onPick(null)}>
            {t('insight.all')}
          </Chip>
        </Reveal>
        {themeData.themes.map((tm, i) => (
          <Reveal key={tm} index={i + 1} step={30}>
            <Chip active={theme === tm} onClick={() => onPick(tm)} count={themeData.counts[tm]}>
              {themeName(tm, lang)}
            </Chip>
          </Reveal>
        ))}
      </div>

      {theme === null && <p className="text-sm text-ink-400">{t('insight.pickTheme')}</p>}
    </>
  )
}

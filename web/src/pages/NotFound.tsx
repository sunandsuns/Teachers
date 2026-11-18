import { Link } from 'react-router-dom'
import { Empty, PageHeader } from '../components/ui'
import { useI18n } from '../i18n'

/**
 * 找不到这一页。
 *
 * **原先没有这一页，未知路由渲染出的是"什么都没有"**——路由表里没有通配项，
 * 于是 `/shelf2`、敲错的地址、别人转来的过期链接，命中不了任何一条路由，
 * 连 `AppShell` 一起都不渲染：整屏纯白，顶栏、页脚、导航一个都没有，
 * 用户唯一的出路是手动改地址栏。写错一个字就走进死胡同，这是实打实的 bug。
 *
 * 所以它被放在 `RequireAuth` + `AppShell` **这一组里面**（见 `App.tsx`）：
 * 走到这里时顶栏还在，用户从导航就能回任何一页。空态本身再给一个回去的按钮，
 * 面向的是"不知道点哪里"的人。
 */
export default function NotFound() {
  const { t } = useI18n()

  return (
    <section>
      <PageHeader title={t('notFound.title')} description={t('notFound.description')} />
      <Empty
        title={t('notFound.empty')}
        hint={t('notFound.hint')}
        action={
          // `Link` 而不是 `Button`：这是一次导航，读屏与"在新标签页打开"都得
          // 按链接来认。样式沿用主按钮那一套 token，视觉上仍是按钮。
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-lg bg-cinnabar-500 px-4 py-2 text-sm font-medium text-paper-50 shadow-card transition-[background-color,transform] duration-quick ease-swift hover:bg-cinnabar-600 active:scale-[0.97]"
          >
            {t('notFound.back')}
          </Link>
        }
      />
    </section>
  )
}

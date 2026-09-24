import { Fragment, useMemo } from 'react'
import { Link, useLocation } from 'react-router-dom'
import UserMenu from '../../features/auth/UserMenu'
import { useAuth } from '../../features/auth/AuthProvider'
import { useI18n } from '../../i18n'
import { useSlidingIndicator } from '../../lib/useSlidingIndicator'
import LangToggle from '../LangToggle'
import { isNavItemActive, navItemsFor } from './nav'

/**
 * 顶栏。
 *
 * 三件事，按重要性排：
 *
 * 1. **滑动指示器**。当前所在页不是"这一项亮了"，而是一块朱砂底**滑过去**。
 *    位置与宽度靠实测（"书架"和"知识库"宽度差一倍，写死必错位），
 *    滑动本身交给 CSS transition 在合成层跑。
 *
 * 2. **导航项只渲染一次**。曾经想过"桌面一排 + 窄屏收进汉堡菜单"，
 *    但那意味着同一份文案在 DOM 里出现两遍——集成测试里
 *    `getByText('寻章')` 会因为匹配到两个而直接失败，读屏也会把导航念两遍。
 *    改成一条**可横向滚动**的导航：窄屏滚，宽屏居中，DOM 始终只有一份。
 *
 * 3. **分组之间一条发丝线**。"资料"（书架/寻章/知识库）与"我的"
 *    （求教/回响/画像/感悟）本是两类事，用一条线隔开比加两个组名更省地方。
 */
export default function TopBar() {
  const { t } = useI18n()
  const { pathname } = useLocation()
  const { user } = useAuth()

  // 导航项按身份算。**先等 `/auth/me` 回来再算**这件事不做特殊处理：
  // 未登录时先少一个「后台」，登录态到达后它自己会出现——多一次极短的
  // 重排，好过让已登录的管理员看到一瞬"没有后台入口"的顶栏。
  const items = useMemo(() => navItemsFor(Boolean(user?.is_admin)), [user])

  const activeIndex = items.findIndex(item => isNavItemActive(pathname, item))
  const { containerRef, rect } = useSlidingIndicator([activeIndex, items.length])

  return (
    <header className="topbar">
      <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-2.5 sm:px-6">
        <Link to="/" className="group flex shrink-0 items-baseline gap-2">
          {/* 产品名保持中文原样：它是这方"书卷"的题字，
              不随界面语言变——就像不会把"微信"在英文界面上写成 WeChat */}
          <span className="font-serif text-xl font-bold tracking-tight text-ink-900 transition-colors duration-quick group-hover:text-cinnabar-600">
            人生导师
          </span>
          <span className="hidden text-xs text-ink-400 lg:inline">{t('app.subtitle')}</span>
        </Link>

        {/* 指示器与滚动容器是**兄弟**而不是父子：
            若把指示器放进 overflow-x-auto 的 nav 里，它会跟着内容一起被滚走，
            横向滚动时位置就错了。挂在外层的相对容器上，实测出的偏移天然
            已经把滚动量算进去了。 */}
        <div ref={containerRef} className="relative min-w-0 flex-1">
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0.5 left-0 rounded-lg bg-cinnabar-500 shadow-card transition-[transform,width,opacity] duration-calm ease-spring"
            style={{
              transform: `translateX(${rect?.left ?? 0}px)`,
              width: rect?.width ?? 0,
              // 首帧量不到（或当前在子页面、没有对应入口）时保持透明，
              // 否则它会从左上角"野跳"过来
              opacity: rect ? 1 : 0,
            }}
          />
          <nav
            aria-label={t('nav.label')}
            className="no-scrollbar flex items-center gap-0.5 overflow-x-auto lg:justify-center"
          >
            {items.map((item, i) => {
              const active = isNavItemActive(pathname, item)
              const startsGroup = i > 0 && items[i - 1].group !== item.group
              return (
                <Fragment key={item.to}>
                  {startsGroup && (
                    <span
                      aria-hidden="true"
                      className="mx-1 h-4 w-px shrink-0 bg-paper-300"
                    />
                  )}
                  <Link
                    to={item.to}
                    aria-current={active ? 'page' : undefined}
                    data-indicator-active={active || undefined}
                    className={`relative shrink-0 rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors duration-quick sm:px-3 ${
                      active
                        ? 'text-paper-50'
                        : 'text-ink-600 hover:bg-paper-200 hover:text-ink-900'
                    }`}
                  >
                    {t(item.key)}
                  </Link>
                </Fragment>
              )
            })}
          </nav>
        </div>

        <span aria-hidden="true" className="hidden h-5 w-px shrink-0 bg-paper-300 sm:block" />
        <LangToggle />
        <UserMenu />
      </div>
    </header>
  )
}

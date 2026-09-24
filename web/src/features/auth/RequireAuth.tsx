import { Outlet, useLocation } from 'react-router-dom'
import { navItemFor } from '../../components/layout/nav'
import { useI18n } from '../../i18n'
import LoginGate from './LoginGate'

/**
 * 「这一组路由需要登录」——一条**无路径的布局路由**。
 *
 * 为什么是布局路由，而不是给每条路由各包一层 `<LoginGate>`
 * --------------------------------------------------------------------------
 * 门禁是"一类页面的共同属性"，就该在路由表里用结构表达出来：
 *
 *   <Route element={<RequireAuth />}>
 *     <Route path="/shelf" element={<Shelf />} />
 *     ...
 *   </Route>
 *
 * 好处有三个，都不是审美问题：
 *   · **一处说了算。** "哪些页面要登录"从此只有路由表这一个答案，加一页
 *     只需挪一行；而"每条路由各包一层"时，答案散在八行里，漏包一条
 *     不会被任何人发现——它只是安静地对匿名开放了。
 *   · **页面保持纯粹。** 各 feature 的内容页不必知道自己被门禁罩着，
 *     单测里渲染 `<SearchPage />` 也不用先搭一套登录态。
 *   · **不改 URL。** 布局路由不占路径段，`/search` 还是 `/search`，
 *     转场方向（按导航次序算）与滚动复位都不受影响。
 *
 * 顺带一提：未登录时 `<Outlet />` 根本不渲染，所以那些按路由分包的页面
 * 连代码都不会去下载——进不去的东西没必要先取回来。
 */
export default function RequireAuth() {
  const { t } = useI18n()
  const { pathname } = useLocation()

  // 点名当前这一页。功能名从导航表里取，而不是在门禁里再维护一份
  // "路径 → 功能名"——那两份迟早对不上。取不到（理论上不会发生）就
  // 退回通用那句，宁可说得泛一点，也不要冒出一个空引号。
  const item = navItemFor(pathname)

  return (
    <LoginGate hint={item ? t('auth.needLoginFor', { name: t(item.key) }) : undefined}>
      <Outlet />
    </LoginGate>
  )
}

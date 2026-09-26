import { lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import AuthLayout from './components/layout/AuthLayout'
import RequireAuth from './features/auth/RequireAuth'

// 页面按路由**分包**：进哪一页才下载哪一页的代码。
//
// 原先八个页面全是静态 import，会被打进同一个 chunk——打开「书架」也得先把
// 画像、知识图谱、阅读器的代码一起下载并解析完，才看得到第一屏。桌面版虽然
// 是本地加载，省下的这点网络时间不算什么，但**解析与执行**同样要花，且每个
// 页面都在为别的页面付这份钱。
//
// 代价是切到没去过的页面时多一次本地取 chunk（几毫秒）。兜底由 `ContentStage`
// 统一提供，所以万一真的慢，看到的也是熟悉的样子，不会白屏。
const Library = lazy(() => import('./pages/Library'))
const Reader = lazy(() => import('./pages/Reader'))
const Advisor = lazy(() => import('./pages/Advisor'))
const History = lazy(() => import('./pages/History'))
const Knowledge = lazy(() => import('./pages/Knowledge'))
const Profile = lazy(() => import('./pages/Profile'))
const Insights = lazy(() => import('./pages/Insights'))
const Search = lazy(() => import('./pages/Search'))
// 「我的书架」与「后台」也按路由分包：多数会话根本不会打开后台，
// 让它跟着首屏一起下载（连带数据库浏览那一大坨）是白花的。
const Shelf = lazy(() => import('./pages/Shelf'))
const Admin = lazy(() => import('./pages/Admin'))
const Login = lazy(() => import('./pages/Login'))
const Register = lazy(() => import('./pages/Register'))

/**
 * 路由表。
 *
 * 这里**只该有路由**。外壳、导航数据、转场、页脚都已经搬去
 * `components/layout/`——所以这个文件现在小到可以一眼看完，
 * 加一页就是在下面加一行。
 *
 * 两块，按"谁能看"分：
 *
 *   · **账号页**：`/login`、`/register`，走 `AuthLayout`——整屏、没有导航栏。
 *     它们自己当然不能要登录，否则进不去。
 *   · **其余全部**：收在一条无路径的 `RequireAuth` 布局路由里，未登录直接
 *     跳到 `/login`。**注意这里是"全部"，包括 `/` 书架与 `/books/:bookId`
 *     阅读页**：这套产品现在的入口就是登录页，登录之前一个页面也看不了。
 *
 * 要不要登录由路由表决定（结构上就看得见，漏包一条不会报错、只会安静地
 * 对匿名开放）；**是不是管理员**留在 `AdminPage` 里——未登录和"已登录但不是
 * 管理员"该看到的话不一样，那句区别只有页面自己说得清。
 */
export default function App() {
  return (
    <Routes>
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<Library />} />
          <Route path="/books/:bookId" element={<Reader />} />
          <Route path="/shelf" element={<Shelf />} />
          <Route path="/search" element={<Search />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/ask" element={<Advisor />} />
          <Route path="/history" element={<History />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/insights" element={<Insights />} />
          <Route path="/admin" element={<Admin />} />
        </Route>
      </Route>
    </Routes>
  )
}

import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import PageStage from './components/layout/PageStage'
import { Loading } from './components/Status'
import RequireAuth from './features/auth/RequireAuth'

// 页面按路由**分包**：进哪一页才下载哪一页的代码。
//
// 原先八个页面全是静态 import，会被打进同一个 chunk——打开「书架」也得先把
// 画像、知识图谱、阅读器的代码一起下载并解析完，才看得到第一屏。桌面版虽然
// 是本地加载，省下的这点网络时间不算什么，但**解析与执行**同样要花，且每个
// 页面都在为别的页面付这份钱。
//
// 代价是切到没去过的页面时多一次本地取 chunk（几毫秒）。Suspense 的兜底
// 用同一个 Loading 组件，所以万一真的慢，看到的也是熟悉的样子，不会白屏。
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
 * 这里**只该有路由**。顶栏、页脚、导航数据、布局宽度都已经搬去
 * `components/layout/`——所以这个文件现在小到可以一眼看完，
 * 加一页就是在下面加一行。
 *
 * 三块，按"谁能看"分：
 *
 *   · **匿名可看**：`/` 书架、`/books/:bookId` 阅读页。
 *     门只开在这两处，是因为书架是这套产品的**门面**：匿名用户能翻书目、
 *     能点开读正文，才知道这里有什么、值不值得注册。反过来，若把阅读页
 *     也拦掉，匿名看到一堆点不开的书名，书架就成了死胡同。
 *   · **要登录**：其余全部，用一条无路径的布局路由圈起来（见 `RequireAuth`）。
 *     把清单写在**结构**里而不是给每条路由包一层，是为了让"哪些页面要登录"
 *     只有一处答案——漏包一条不会报错，只会安静地对匿名开放。
 *   · **账号页**：`/login`、`/register` 本身当然不能要登录，否则进不去。
 *
 * 权限判断分两层，各管各的：**要不要登录**由路由表决定（结构上就看得见）；
 * **是不是管理员**留在 `AdminPage` 里——未登录和"已登录但不是管理员"该看到
 * 的话不一样，那句区别只有页面自己说得清。
 *
 * `Suspense` 在 `PageStage` **里面**：分包还没下载完时，兜底要出现在那个
 * 正在滑入的框里，而不是把整个舞台换成兜底——后者会把转场动画一起冲掉。
 */
export default function App() {
  return (
    <AppShell>
      <PageStage>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<Library />} />
            <Route path="/books/:bookId" element={<Reader />} />

            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            <Route element={<RequireAuth />}>
              <Route path="/shelf" element={<Shelf />} />
              <Route path="/search" element={<Search />} />
              <Route path="/knowledge" element={<Knowledge />} />
              <Route path="/ask" element={<Advisor />} />
              <Route path="/history" element={<History />} />
              <Route path="/profile" element={<Profile />} />
              <Route path="/insights" element={<Insights />} />
              <Route path="/admin" element={<Admin />} />
            </Route>
          </Routes>
        </Suspense>
      </PageStage>
    </AppShell>
  )
}

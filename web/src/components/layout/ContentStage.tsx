import { Suspense } from 'react'
import { Outlet } from 'react-router-dom'
import { Loading } from '../Status'
import PageStage from './PageStage'

/**
 * 内容舞台：**转场动画 + 分包兜底**，合成一处。
 *
 * 为什么要有这么一个东西
 * --------------------------------------------------------------------------
 * 路由表现在有两种外壳——正式界面用 `AppShell`（顶栏 + 正文 + 页脚），
 * 登录/注册用 `AuthLayout`（整屏，没有导航）。两种外壳的"外面"不一样，
 * "里面"却必须一模一样：
 *
 *   1. 换页要演转场（`PageStage`）；
 *   2. 页面是按路由分包的，chunk 还没下载完时兜底要出现在**正在滑入的那个
 *      框里**，而不是把整块内容换成兜底（后者会把转场动画一起冲掉）。
 *
 * 这两件事一起写在两个外壳文件里，就成了"改一处忘一处"的隐患——而它们
 * 本身与"外壳长什么样"无关，所以抽出来，两边都只写 `<ContentStage />`。
 *
 * 它渲染的是 `<Outlet />`，所以只能放在布局路由的**元素内部**（`AppShell`
 * 与 `AuthLayout` 都是布局路由）。
 */
export default function ContentStage() {
  return (
    <PageStage>
      <Suspense fallback={<Loading />}>
        <Outlet />
      </Suspense>
    </PageStage>
  )
}

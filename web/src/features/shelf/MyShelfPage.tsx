import LoginGate from '../auth/LoginGate'
import ShelfPage from './ShelfPage'

/**
 * 「我的书架」的路由入口。
 *
 * 把"需要登录"这层门禁放在这里，而不是塞进 `ShelfPage` 里：后者是一个纯粹
 * 的内容页——给它一份数据它就能渲染，测试里不必为了看它一眼先搭一套登录态。
 * 门禁与内容分开，两件事各自都能单独说清楚。
 */
export default function MyShelfPage() {
  return (
    <LoginGate>
      <ShelfPage />
    </LoginGate>
  )
}

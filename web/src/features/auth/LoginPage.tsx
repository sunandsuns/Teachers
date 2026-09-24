import AuthPage from './AuthPage'

/**
 * 登录页。
 *
 * 与注册页共用 `AuthPage`，这里只负责钉死模式。做成两个薄壳而不是在路由里
 * 写 `<AuthPage mode="login" />`，是为了让路由文件与页面薄壳保持"一行挂载"
 * 的一致形状——路由表里不该出现 props。
 */
export default function LoginPage() {
  return <AuthPage mode="login" />
}

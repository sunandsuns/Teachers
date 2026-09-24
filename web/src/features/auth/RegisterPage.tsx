import AuthPage from './AuthPage'

/** 注册页。与登录页共用 `AuthPage`，见 `LoginPage` 的说明。 */
export default function RegisterPage() {
  return <AuthPage mode="register" />
}

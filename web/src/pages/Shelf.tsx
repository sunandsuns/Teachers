/**
 * 路由薄壳。实现见 `features/shelf/ShelfPage`。
 *
 * 登录门禁**不在这一层**——它在路由表上（`App.tsx` 里 `RequireAuth` 圈住的那一组）。
 * 曾经这里包着一个 `MyShelfPage`，把门禁和内容绑在一起；门禁上移到路由后，
 * 那一层就只剩空转发，删掉了。现在"哪些页面要登录"只有路由表一个答案。
 */
export { default } from '../features/shelf/ShelfPage'

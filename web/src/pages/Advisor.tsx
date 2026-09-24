/**
 * 路由薄壳。实现见 `features/advisor/`。
 *
 * 保留这一层是为了让 `pages/Advisor` 这个引用路径不变——
 * 测试与路由都按它取模块。
 */
export { default } from '../features/advisor/AdvisorPage'

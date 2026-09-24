/**
 * 路由薄壳。
 *
 * 页面实现已经搬到 `features/library/`——那里才是它的归属：一个 feature
 * 自带它的组件、数据钩子与文案，删掉整个目录不会波及别的页面。
 *
 * 这个文件保留下来只有一个理由：**路径稳定**。测试与路由都按
 * `pages/Library` 引用它，重定向一次就要改一圈调用点，不划算。
 * 所以它的职责就是"把 feature 挂到路由上"，一行。
 */
export { default } from '../features/library/LibraryPage'

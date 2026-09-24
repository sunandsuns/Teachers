/** 「回响」页的路由薄壳。
 *
 * 实现搬去了 `features/history/`，这里只留一行再导出。
 * 之所以不删掉这个文件：路由与测试都按 `pages/History` 取模块，
 * 保留薄壳，重构才是**可增量**的——没迁完的页面照样跑得起来。
 *
 * 页面本身的说明（契约、为什么按话题聚合）见
 * `features/history/HistoryPage.tsx`。
 */
export { default } from '../features/history/HistoryPage'

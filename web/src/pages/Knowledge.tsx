/**
 * 路由外壳。真实实现在 features/knowledge/KnowledgePage。
 *
 * 保留这一层是为了让路由与测试的 import 路径保持稳定——迁移可以一个页面一个
 * 页面地做，不必一次性改掉全站的引用。
 */
export { default } from '../features/knowledge/KnowledgePage'

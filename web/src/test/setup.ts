import '@testing-library/jest-dom'
import { configure } from '@testing-library/dom'
import { beforeEach, vi } from 'vitest'

// `findBy*` / `waitFor` 默认只等 1 秒。
//
// 八个页面都是**路由懒加载**的，在 vitest 里这意味着一次真正的 `import()`——
// 而测试运行器是"用到哪个文件才转译哪个"，冷启动 + 多文件并行时，
// 这一次动态导入偶尔会超过 1 秒。表现是**随机几个用例失败**，DOM 停在
// 「加载中…」，重跑又全绿——极难排查，也让人不敢信这套测试。
//
// 放宽到 5 秒只是给等待留余地，**不改变任何断言**：真要找不到，
// 5 秒后照样失败，只是失败得可信。
configure({ asyncUtilTimeout: 5000 })

// jsdom 没有实现 scrollIntoView；组件里用它做"滚动到底部"，
// 不补这个桩会在用例结束后抛出未捕获异常。
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn()
}

// jsdom 也没有实现 confirm：调用它会往控制台打一条 "Not implemented" 再返回
// undefined。组件用它给"清空历史"这类不可撤销的操作做二次确认，这里补一个
// **默认拒绝**的桩——需要放行的用例自己 spyOn 覆盖，免得"忘了拦"反而把测试
// 会去点真正的破坏性动作。
if (!window.confirm) {
  window.confirm = () => false
}

// 滚动同理，但**不能**用上面那种 `if (!window.scrollTo)` 的写法：jsdom 是
// **定义了**这个方法的，只是它的实现就是"打一句 Not implemented 然后什么都不做"。
// 换模块时舞台要用它把新页面拉回顶部（`PageStage` 的 `useLayoutEffect`），
// 于是每个渲染 `App` 的用例都会在控制台留一段红字堆栈——真出错时反而看不见。
// 所以这里无条件盖掉。
window.scrollTo = vi.fn() as unknown as typeof window.scrollTo

// 模型设置存在 localStorage 里，用例之间会互相串（前一个用例填的 Key
// 会让后一个用例的请求带上自定义端点）。每个用例前清空。
beforeEach(() => {
  window.localStorage.clear()
})

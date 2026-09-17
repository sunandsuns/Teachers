import '@testing-library/jest-dom'
import { beforeEach, vi } from 'vitest'

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

// 模型设置存在 localStorage 里，用例之间会互相串（前一个用例填的 Key
// 会让后一个用例的请求带上自定义端点）。每个用例前清空。
beforeEach(() => {
  window.localStorage.clear()
})

import '@testing-library/jest-dom'
import { beforeEach, vi } from 'vitest'

// jsdom 没有实现 scrollIntoView；组件里用它做"滚动到底部"，
// 不补这个桩会在用例结束后抛出未捕获异常。
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn()
}

// 模型设置存在 localStorage 里，用例之间会互相串（前一个用例填的 Key
// 会让后一个用例的请求带上自定义端点）。每个用例前清空。
beforeEach(() => {
  window.localStorage.clear()
})

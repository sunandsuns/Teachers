import '@testing-library/jest-dom'
import { vi } from 'vitest'

// jsdom 没有实现 scrollIntoView；组件里用它做"滚动到底部"，
// 不补这个桩会在用例结束后抛出未捕获异常。
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn()
}

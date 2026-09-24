import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import PageStage from '../components/layout/PageStage'
import { transitionDirection } from '../components/layout/nav'

/**
 * 换模块的转场。
 *
 * 两件事分开测：
 *   1. `transitionDirection` 是纯函数，"往哪演"完全由它决定，先把这张表钉死；
 *   2. `PageStage` 只负责"把方向变成类名"和"顺手把滚动拉回顶部"。
 *
 * jsdom 不会真的跑 CSS 动画，所以这里断言的是**动画有没有被挂上、挂的是哪一个**
 * ——真正的观感得靠 `ui_check.py` 在真实浏览器里截图看（见 README「联调冒烟」）。
 */

function Harness({ initial = '/' }: { initial?: string }) {
  return (
    <MemoryRouter initialEntries={[initial]}>
      <PageStage>
        <Routes>
          <Route path="/" element={<p>书架页</p>} />
          <Route path="/ask" element={<p>求教页</p>} />
          <Route path="/search" element={<p>寻章页</p>} />
          <Route path="/login" element={<p>登录页</p>} />
          <Route path="/books/:bookId" element={<p>阅读页</p>} />
        </Routes>
      </PageStage>
      <nav>
        <Link to="/">去书架</Link>
        <Link to="/ask">去求教</Link>
        <Link to="/search?q=a">查 a</Link>
        <Link to="/search?q=b">查 b</Link>
        <Link to="/login">去登录</Link>
        <Link to="/books/01">读 01</Link>
        <Link to="/books/02">读 02</Link>
      </nav>
    </MemoryRouter>
  )
}

/** 当前的转场框。`PageStage` 会给它挂 `data-page-frame`。 */
function frame(): HTMLElement {
  const el = document.querySelector('[data-page-frame]')
  if (!el) throw new Error('没有找到转场框')
  return el as HTMLElement
}

/** 当前演的是哪个方向。首帧不演，返回 `'static'`。 */
function direction(): string {
  return frame().dataset.pageFrame ?? ''
}

let scrollTo: ReturnType<typeof vi.fn>

beforeEach(() => {
  // 全局 setup 已经盖掉 jsdom 那个"没实现"的 `window.scrollTo` 了，
  // 这里再换一个新的，是为了**拿到这个 mock 的句柄**好断言它有没有被调用、
  // 参数是什么。全局那个桩只是为了让控制台安静。
  scrollTo = vi.fn()
  window.scrollTo = scrollTo as unknown as typeof window.scrollTo
})

describe('transitionDirection：方向由导航次序决定', () => {
  it('往导航右边走是 forward', () => {
    expect(transitionDirection('/', '/ask')).toBe('forward')
    expect(transitionDirection('/ask', '/insights')).toBe('forward')
  })

  it('往导航左边走是 back', () => {
    expect(transitionDirection('/ask', '/')).toBe('back')
    expect(transitionDirection('/insights', '/search')).toBe('back')
  })

  it('管理员入口排在最后，因此从书架过去是 forward', () => {
    // 后台那一项不在 NAV_ITEMS 里，但确实显示在最右边——次序得跟着实际排布，
    // 否则从书架点「后台」会往左演，方向就和眼睛看到的相反了。
    expect(transitionDirection('/', '/admin')).toBe('forward')
    expect(transitionDirection('/admin', '/')).toBe('back')
  })

  it('不在导航上的页面一律走纵深', () => {
    // 登录、注册是"进去一下再出来"的地方，横向没有可比的位置。
    expect(transitionDirection('/', '/login')).toBe('depth')
    expect(transitionDirection('/login', '/')).toBe('depth')
  })

  it('同一个导航项内部换页也是纵深', () => {
    // 翻到下一章：读者的直觉是往下走，不是往旁边走。
    expect(transitionDirection('/books/01', '/books/02')).toBe('depth')
    expect(transitionDirection('/search', '/search')).toBe('depth')
  })

  it('子路径归到它的父级入口', () => {
    // `/books/01` 属于「书架」，所以从它去「求教」是 forward，而不是纵深。
    expect(transitionDirection('/books/01', '/ask')).toBe('forward')
    expect(transitionDirection('/ask', '/books/01')).toBe('back')
  })
})

describe('PageStage：把方向挂成动画类', () => {
  it('首帧不演动画', () => {
    // 第一次进页面时内容自己会入场（各页的 Reveal），舞台再演一遍就成了
    // "整页淡入 + 卡片依次升起"两层叠加，反而拖沓。
    render(<Harness />)
    expect(direction()).toBe('static')
  })

  it('往右换模块时从右侧进来', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('link', { name: '去求教' }))
    expect(await screen.findByText('求教页')).toBeInTheDocument()
    expect(direction()).toBe('forward')
  })

  it('往左换模块时从左侧进来', async () => {
    const user = userEvent.setup()
    render(<Harness initial="/ask" />)
    await user.click(screen.getByRole('link', { name: '去书架' }))
    expect(await screen.findByText('书架页')).toBeInTheDocument()
    expect(direction()).toBe('back')
  })

  it('进不在导航上的页面时自下浮起', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('link', { name: '去登录' }))
    expect(await screen.findByText('登录页')).toBeInTheDocument()
    expect(direction()).toBe('depth')
  })

  it('换模块会把滚动拉回顶部', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('link', { name: '去求教' }))
    expect(scrollTo).toHaveBeenCalledWith(0, 0)
  })

  it('首次进入不抢滚动位置', () => {
    // 初始那条是 POP（浏览器自己负责恢复滚动），这里再插一脚会打掉
    // "后退回到原位"的预期。
    render(<Harness />)
    expect(scrollTo).not.toHaveBeenCalled()
  })

  it('只变查询串时既不重挂也不重演', async () => {
    // `/search?q=a` → `?q=b` 是同一页在换内容，不该被当成换模块：
    // 重挂会丢掉页面状态（输入框、已展开的条目），重演动画则会闪一下。
    const user = userEvent.setup()
    render(<Harness initial="/search" />)
    const before = frame()
    expect(direction()).toBe('static')

    await user.click(screen.getByRole('link', { name: '查 a' }))
    await user.click(screen.getByRole('link', { name: '查 b' }))

    expect(frame()).toBe(before)
    expect(direction()).toBe('static')
  })

  it('换模块时确实是新的一棵树', async () => {
    // 与上一条相对：路径变了就该重挂，否则旧页面的状态会漏到新页面里。
    const user = userEvent.setup()
    render(<Harness initial="/books/01" />)
    const before = frame()
    await user.click(screen.getByRole('link', { name: '读 02' }))
    expect(await screen.findByText('阅读页')).toBeInTheDocument()
    expect(frame()).not.toBe(before)
    expect(direction()).toBe('depth')
  })
})

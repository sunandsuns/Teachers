import { useLayoutEffect, useState, type ReactNode } from 'react'
import { useLocation, useNavigationType } from 'react-router-dom'
import { transitionDirection, type TransitionDirection } from './nav'

/**
 * 页面舞台：换模块时，新页面按"行进方向"滑进来。
 *
 * 方向不是随便挑的，是**导航的空间次序**算出来的：从左边的模块去右边的模块，
 * 内容就从右侧进来；往回走就从左侧进来。这样转场表达的是"我在往哪走"，
 * 而不是"这里有个特效"。方向的算法在 `nav.ts` 的 `transitionDirection`。
 *
 * ── 为什么只做入场，不做退场 ──────────────────────────────────────────
 *
 * 退场（旧页面一边淡出一边让开）看着更"完整"，但它要付出三样东西，每一样
 * 都会牵连到别处：
 *
 *   1. 旧页面得继续挂在 DOM 里。页面里有两处 `sticky`（求教的底部输入栏、
 *      阅读页的章节目录），两套滚动上下文同时活着会互相打架。
 *   2. 要裁掉旧页面溢出的部分就得给舞台加 `overflow: hidden`——而
 *      `overflow: hidden` 会让舞台**变成滚动容器**，`sticky bottom-4` 的
 *      输入栏会改粘在舞台底部，不再粘在视口底部。这是肉眼可见的坏掉。
 *   3. 旧页面还得从"用户当时看的位置"淡出，否则滚到一半换页时，
 *      淡出的会是那页的开头——于是又得把 `scrollY` 量下来做补偿。
 *
 * 而入场的收益占了九成：方向感、位移、层次，全在入场里。所以这里让旧页面
 * 直接卸载，新页面滑进来，一行不裁、零副作用。
 *
 * 舞台本身只加 `overflow-x: clip`，挡住横向滑入时那 34px 的溢出。
 * 用 `clip` 而不是 `hidden`：`clip` **不会**建立滚动容器（见上面第 2 条）。
 *
 * ── 与顶栏的关系 ─────────────────────────────────────────────────────
 *
 * 动画时长与缓动刻意和顶栏的滑动指示器一致（320ms / expo-out）。指示器也在
 * 同一时间滑到新位置，两边同起同落，整屏看起来是一个动作。
 */

/** 方向 → 动画类。
 *
 *  类名必须写成完整的字面量：Tailwind 是靠扫源码里的字符串生成 CSS 的，
 *  用模板串拼出来的类名它扫不到，动画会静默失效。 */
const ANIMATION: Record<TransitionDirection, string> = {
  forward: 'animate-stage-forward',
  back: 'animate-stage-back',
  depth: 'animate-stage-depth',
}

export default function PageStage({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const navigationType = useNavigationType()

  // 「上一次渲染的是哪个路径」与「这次该往哪演」。
  //
  // 用 state 而不是 ref，并且**在渲染期直接改**：这是 React 官方认可的
  // "从 props 派生 state" 写法。好处是新页面的**第一次**渲染就已经带着正确的
  // 方向类，不会先按默认方向画一帧、再改成正确方向（那会看到一次抖动）。
  const [current, setCurrent] = useState(pathname)
  const [direction, setDirection] = useState<TransitionDirection | null>(null)

  if (current !== pathname) {
    setDirection(transitionDirection(current, pathname))
    setCurrent(pathname)
  }

  // 换页回到顶部。
  //
  // 不做这件事的话，转场会暴露一个本来就有的问题：在书架滚到一半点「求教」，
  // 新页面会在**同样的滚动位置**出现——如果那一页更短，浏览器把滚动量一夹，
  // 你看到的就是它的底部。转场本来就在说"我换了个地方"，那就该从那个地方的
  // 开头看起。
  //
  // 只在 PUSH 时做：后退/前进由浏览器自己的滚动恢复负责，这里再插一脚会把
  // 用户回到原位的预期打掉。用 `useLayoutEffect` 是为了赶在浏览器绘制之前
  // 完成，否则会先画一帧旧的滚动位置。
  useLayoutEffect(() => {
    if (navigationType === 'PUSH') window.scrollTo(0, 0)
  }, [pathname, navigationType])

  return (
    <div className="[overflow-x:clip]">
      {/* `key` 用路径而不是别的：路径一变就该是一棵新的树。
          同一个路径只变查询串（`/search?q=a` → `?q=b`）时 key 不变，
          因此不会重挂、也不会重演动画——那是同一页在换内容。

          `data-page-frame` 让这一层在 DOM 里可辨认：测试要断言"往哪个方向演"，
          而类名会被 Tailwind 的生成顺序影响，靠 `[class*=...]` 找不稳。 */}
      <div
        key={pathname}
        data-page-frame={direction ?? 'static'}
        className={direction ? ANIMATION[direction] : undefined}
      >
        {children}
      </div>
    </div>
  )
}

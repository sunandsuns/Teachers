import type { CSSProperties } from 'react'

/**
 * 运动系统。
 *
 * 只做一件事：把"动画该怎么走"从组件里抽出来，收成一组具名常量与纯函数。
 * 组件不该再出现 `transition: all .3s ease` 这种各自为政的写法——那正是
 * "每个页面动得都不一样、拼起来很廉价"的来源。
 *
 * 为什么不引 framer-motion：
 *   1. 这个项目刻意走零重依赖（连检索都是自建的），为几个入场动画引一个
 *      几十 KB 的运行时，和既有取向冲突；
 *   2. 我们要的动效**全部**能用 CSS 表达（位移 / 缩放 / 透明度 / 高度），
 *      JS 只需要"决定何时开始"，那是 IntersectionObserver 的活；
 *   3. CSS 动画跑在合成层，不占主线程。列表滚动时不会和 React 渲染抢时间，
 *      这是"流畅"的物理前提。
 *
 * 唯一的例外是「滑动指示器」（见 `useSlidingIndicator`）：它要知道
 * 目标元素的真实位置，只能量。但那也只是量一次几何，不参与逐帧计算。
 */

/** 缓动曲线。与 `tailwind.config.js` 的 `transitionTimingFunction` 同源，
 *  这里再列一份是给"必须在 JS 里写 transition"的场景用（如滑动指示器）。 */
export const EASE = {
  /** 进出对称，适合会来回的 hover */
  swift: 'cubic-bezier(0.4, 0, 0.2, 1)',
  /** 招牌曲线：起手快、收尾极缓。入场与"移动到新位置"都用它 */
  spring: 'cubic-bezier(0.16, 1, 0.3, 1)',
  /** 轻微过冲，只给小元件 */
  bounce: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
} as const

/** 时长（毫秒）。与 tailwind.config.js 的 `transitionDuration` 同源。 */
export const DURATION = {
  snap: 120,
  quick: 200,
  calm: 320,
  slow: 520,
} as const

/**
 * 错峰入场：第 `index` 个元素的延迟毫秒数。
 *
 * 一排卡片同时淡入会像"整块闪了一下"；每张错开 40ms 左右，眼睛就能读出
 * "它们是一个一个来的"，这是列表入场显高级的关键，代价是零。
 *
 * `max` 是上限：一屏几十张卡时，若严格按 `index * step` 排下去，
 * 最后一张要等两秒才出现——用户早就滚过去了。所以超过上限就**并列**，
 * 让靠后的元素一起落位。
 */
export function stagger(index: number, step = 45, max = 360): number {
  return Math.min(index * step, max)
}

/** `stagger` 的样式包装：直接塞进 `style` 里用。
 *
 *  为什么用行内 style 而不是给每个下标生成一个类：
 *  Tailwind 扫不到运行时算出来的类名，且为 0..20 各写一条 `delay-[45ms]`
 *  是纯噪音。延迟是**数据**，就该走 style。 */
export function delayStyle(index: number, step = 45, max = 360): CSSProperties {
  return { animationDelay: `${stagger(index, step, max)}ms` }
}

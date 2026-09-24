import { useEffect, useRef, useState, type RefObject } from 'react'

/**
 * 元素是否进入过视口。用于"滚到才入场"的揭示动画。
 *
 * 三个刻意的设计：
 *
 * 1. **只触发一次**（`once`）。滚上去再滚回来不该重新演一遍——重复入场
 *    会让人觉得自己在跟界面搏斗。默认就锁死，不做成可选项。
 *
 * 2. **没有 IntersectionObserver 时直接返回 true**。jsdom 里没有这个 API，
 *    若兜底成 false，所有内容在测试里都是隐藏的，断言全部失效。
 *    真机上它也只在极老的浏览器缺失，那时让内容直接显示是正确的降级。
 *
 * 3. **`rootMargin` 提前 80px 触发**。等元素贴到视口边缘才开始，动画的
 *    前半程会被"还没滚到"浪费掉，看到的是动画后半段；提前一点开始，
 *    元素真正进入视野时正好落到终态，观感是"它本来就在那儿"。
 */
export function useInView<T extends HTMLElement>(
  options: { rootMargin?: string; threshold?: number } = {},
): [RefObject<T>, boolean] {
  const { rootMargin = '0px 0px -80px 0px', threshold = 0.01 } = options
  const ref = useRef<T>(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (inView) return
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true)
      return
    }

    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true)
            observer.disconnect()
          }
        }
      },
      { rootMargin, threshold },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [inView, rootMargin, threshold])

  return [ref, inView]
}

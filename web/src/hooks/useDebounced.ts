import { useEffect, useState } from 'react'

/** 把频繁变化的值延后一会儿再交出去。
 *
 * 用在"输入框每敲一个字就发一次请求"的地方：停手 `delay` 毫秒后才把值放行，
 * 中途还改主意就把上一个定时器清掉——于是"bob"是**一次**请求，而不是三次。
 *
 * 返回值同时用作 `useAsync` 的依赖：它只在真正稳定下来后才变，所以 effect
 * 不会因为"输入框重渲染"而重跑。乱序返回的旧请求由 `useAsync` 的 `cancelled`
 * 兜住（依赖一变，上一轮的响应就被丢弃）。
 */
export function useDebounced<T>(value: T, delay = 300): T {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])

  return settled
}

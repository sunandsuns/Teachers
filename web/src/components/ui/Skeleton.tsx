/**
 * 骨架屏。
 *
 * 用它替代"转圈 + 加载中…"的场景：**已知内容长什么样**的地方（书目网格、
 * 记录列表）应当先把版式撑出来，让页面在数据到达前就是稳定的，数据一到
 * 只是把灰块换成内容，不会整页跳一下。
 *
 * 反过来说，**不知道**内容长什么样的地方（例如一次检索的结果）仍该用转圈——
 * 画一堆形状不对的灰块，只会让人以为页面画错了。
 *
 * 全部标 aria-hidden：这是纯视觉占位，读屏应当只念容器上的 `aria-busy`。
 */
export function Skeleton({ className = '' }: { className?: string }) {
  return <div aria-hidden="true" className={`skeleton ${className}`} />
}

/** 多行文字的占位。最后一行故意短一截——齐平的话像一段被涂掉的文字。 */
export function SkeletonText({ lines = 3, className = '' }: { lines?: number; className?: string }) {
  return (
    <div aria-hidden="true" className={`space-y-2.5 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className={`skeleton h-3.5 ${i === lines - 1 ? 'w-2/5' : 'w-full'}`} />
      ))}
    </div>
  )
}

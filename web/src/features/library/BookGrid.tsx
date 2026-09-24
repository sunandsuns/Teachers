import type { BookSummary } from '../../api/client'
import { Reveal, Skeleton } from '../../components/ui'
import BookCard from './BookCard'

const GRID = 'grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-5 lg:grid-cols-3'

/**
 * 书目网格。入场时逐张错峰浮现（每张晚 45ms，封顶 360ms）。
 *
 * 为什么封顶：一屏 40 本时若严格按序排下去，最后一张要等近两秒才出现，
 * 而用户早就滚到别处了。超过上限就并列落位。
 */
export function BookGrid({ books }: { books: BookSummary[] }) {
  return (
    <div className={GRID}>
      {books.map((book, i) => (
        // Reveal 就是这一格的容器：`flex` 让它撑满行高，
        // 里面的卡片再靠 `w-full` 铺开——这样同一行的卡片高度才是齐的。
        <Reveal key={book.book_id} index={i} className="flex">
          <BookCard book={book} />
        </Reveal>
      ))}
    </div>
  )
}

/**
 * 载入态用骨架屏而不是转圈。
 *
 * 书架的版式是**已知**的（就是下面那个网格），所以先把格子撑出来，
 * 数据一到只是把灰块换成内容，页面不会整页跳一下。
 * 反过来，形状未知的地方（例如检索结果）仍该用转圈——画错形状的灰块
 * 只会让人以为页面画坏了。
 */
export function BookGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className={GRID} aria-busy="true">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card flex flex-col p-5">
          <div className="mb-3 flex items-start justify-between gap-3">
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
          <Skeleton className="h-3.5 w-16" />
          <Skeleton className="mt-auto h-3 w-28" />
        </div>
      ))}
    </div>
  )
}

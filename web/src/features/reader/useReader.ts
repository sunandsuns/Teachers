import { useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api, peek } from '../../api/client'
import { useAsync } from '../../hooks/useAsync'
import { useSourceReader } from './useSourceReader'

export type ReaderTab = 'notes' | 'source'

/**
 * 阅读页的状态与取数。**这一块里唯一碰 `api.*` 的地方。**
 *
 * 三种入口都从 URL 进来，所以初始状态一律**由 searchParams 决定**：
 *
 *   /books/13            → 笔记页签，未选章节
 *   /books/13?chapter=04 → 笔记页签，直接打开第四章（寻章的笔记命中）
 *   /books/13?tab=source&offset=120000 → 原典页签，从第 12 万字读起（寻章的原典命中）
 *
 * 注意 `chapterId` / `tab` 之后是**受控状态**：URL 只决定初值，用户点选由本地
 * 状态接管。否则每点一次章节都要写 URL，会往历史里塞一堆记录。
 */
export function useReader() {
  const { bookId = '' } = useParams()
  const [searchParams] = useSearchParams()

  const [chapterId, setChapterId] = useState<string | null>(searchParams.get('chapter'))
  const [tab, setTab] = useState<ReaderTab>(
    searchParams.get('tab') === 'source' ? 'source' : 'notes',
  )
  //: 深链定位。`|| 0` 兜住 "offset=abc" 这类脏参数，别让 NaN 流进请求
  const sourceOffset = Number(searchParams.get('offset') ?? 0) || 0

  // 下面三处带上 `peek`：书目、章节列表、章节正文都在 GET 缓存里，切回这本书时
  // 首帧直接出内容，不必先闪一帧骨架屏。
  const { data: book, error: bookError, loading: bookLoading } = useAsync(
    () => api.getBook(bookId),
    [bookId],
    () => peek.getBook(bookId),
  )
  const { data: chapters, error: chaptersError } = useAsync(
    () => api.listChapters(bookId),
    [bookId],
    () => peek.listChapters(bookId),
  )
  //: 只有切到原典页签才真去拉正文——笔记页签不该为它付一次请求。
  //: 它**自己**在内部接缓存快照（切回原典页签不再闪那一帧），所以这里没有
  //: 第三参数可传：`text` 是分块累加出来的，不是一次拿到的。
  const source = useSourceReader(bookId, tab === 'source', sourceOffset)

  const current = useMemo(
    () => chapters?.find(ch => ch.chapter_id === chapterId) ?? null,
    [chapters, chapterId],
  )
  const { data: chapterDetail } = useAsync(
    () => (current ? api.getChapter(bookId, current.chapter_id) : Promise.resolve(null)),
    [bookId, current?.chapter_id],
    // 没有选中章节时明确返回 `undefined`（"手上没有"），而不是 `null`（"查到了，
    // 值是空"）——`null` 会被 useAsync 当成有效的缓存命中，把上一章的正文留下。
    () => (current ? peek.getChapter(bookId, current.chapter_id) : undefined),
  )

  //: 只有篇幅超过一块的原典才需要显示翻页进度
  const paginated = source.total > source.chunkSize && source.chunkSize > 0
  //: 已读字数。最后一块常常不满，直接相加会超出总数，所以取小
  const loaded = Math.min(source.startOffset + source.text.length, source.total)

  return {
    book,
    bookError,
    bookLoading,
    chapters,
    chaptersError,
    chapterId,
    setChapterId,
    tab,
    setTab,
    chapterDetail,
    source,
    paginated,
    loaded,
  }
}

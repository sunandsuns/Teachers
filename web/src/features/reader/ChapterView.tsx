import type { ChapterDetail } from '../../api/client'
import Markdown from '../../components/Markdown'
import { Empty } from '../../components/ui'
import { useI18n } from '../../i18n'

/**
 * 笔记正文。
 *
 * 标题与正文之间用一条**发丝线**分隔，而不是靠加大间距：中文正文的行距本就宽，
 * 只靠留白的话，章节标题看起来会像正文的第一段。
 *
 * 未选章节时给空态而不是留白——一片空白会让人以为加载卡住了。
 */
export default function ChapterView({ chapter }: { chapter: ChapterDetail | null }) {
  const { t } = useI18n()

  return (
    <article className="card min-w-0 flex-1 p-6 sm:p-8">
      {chapter ? (
        <>
          <h2 className="mb-6 border-b border-paper-300 pb-3 font-serif text-xl font-bold text-balance text-ink-900">
            {chapter.title}
          </h2>
          <Markdown content={chapter.content} />
        </>
      ) : (
        <Empty
          title={t('reader.pickChapter')}
          icon={
            <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
              <path d="M4 3.5A1.5 1.5 0 015.5 2h6A1.5 1.5 0 0113 3.5V4h1.5A1.5 1.5 0 0116 5.5v11a1.5 1.5 0 01-1.5 1.5h-9A1.5 1.5 0 014 16.5v-13zm2 0v13h9v-11H13v9a.75.75 0 01-1.2.6L10 13.9l-1.8 1.2A.75.75 0 017 14.5v-9H6v-2z" />
            </svg>
          }
        />
      )}
    </article>
  )
}

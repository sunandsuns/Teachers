import { Link } from 'react-router-dom'
import { Empty } from '../../components/ui'
import { ErrorBox, Loading } from '../../components/Status'
import { useI18n } from '../../i18n'
import BookHeader from './BookHeader'
import ChapterList from './ChapterList'
import ChapterView from './ChapterView'
import SourceView from './SourceView'
import { useReader } from './useReader'

/**
 * 阅读：一本书的两副面孔——「理解笔记」与「原典全文」。
 *
 * 编排层只做三件事：把 hook 的状态摊给子组件、把子组件的回调接回 hook、
 * 决定"此刻该显示哪一块"。
 *
 * 页面的三种终态，顺序即优先级：
 *   载入中 → 转圈（书都还不知道是哪本，无从给骨架）
 *   出错   → 错误框
 *   没这本书 → 空态 + 回书架的出口
 *
 * 三种都过了才谈"笔记还是原典"——把错误挡在页签之前，用户就不会在一个
 * 已经坏掉的页面上反复切页签找原因。
 */
export default function ReaderPage() {
  const { t } = useI18n()
  const {
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
  } = useReader()

  if (bookLoading) return <Loading />
  if (bookError) return <ErrorBox message={bookError} />
  if (!book) {
    return (
      <Empty
        title={t('reader.notFound')}
        action={
          <Link
            to="/"
            className="inline-flex items-center rounded-lg border border-paper-300 px-4 py-2 text-sm text-ink-600 transition-colors duration-quick ease-swift hover:border-cinnabar-300 hover:text-cinnabar-600"
          >
            {t('reader.back')}
          </Link>
        }
      />
    )
  }

  return (
    <section>
      <BookHeader book={book} tab={tab} onTabChange={setTab} />

      {tab === 'notes' ? (
        <div className="flex flex-col gap-6 lg:flex-row">
          <ChapterList
            chapters={chapters}
            chapterId={chapterId}
            error={chaptersError}
            onPick={setChapterId}
          />
          <ChapterView chapter={chapterDetail} />
        </div>
      ) : (
        <SourceView source={source} paginated={paginated} loaded={loaded} />
      )}
    </section>
  )
}

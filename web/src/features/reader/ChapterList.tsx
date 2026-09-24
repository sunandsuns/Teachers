import type { ChapterSummary } from '../../api/client'
import { useI18n } from '../../i18n'
import { delayStyle } from '../../lib/motion'

/**
 * 章节目录。
 *
 * 选中态同时给了三样东西：朱砂底、加粗、以及**左侧一道会从中间长出来的竖线**
 * （`scale-y-0 → scale-y-100`）。只靠底色的话，一屏十几个条目里"我在哪一章"
 * 需要逐行比对；有了竖线，视线扫过左边缘就能定位。
 *
 * 竖线用 `origin-center` 而不是 `origin-top`：目录条目很矮（约 36px），
 * 从中间展开比从上往下"刷"下来更利落。
 *
 * 列表整体做**极轻的错峰入场**（step 12ms，上限 240ms）。目录可能有上百条，
 * 步长稍大就会让第 50 条等上半秒——上限是必须的。
 */
export default function ChapterList({
  chapters,
  chapterId,
  error,
  onPick,
}: {
  chapters: ChapterSummary[] | null
  chapterId: string | null
  error: string | null
  onPick: (chapterId: string) => void
}) {
  const { t } = useI18n()

  return (
    <nav className="lg:w-64 lg:shrink-0" aria-label={t('reader.chapterList')}>
      <div className="card overflow-hidden lg:sticky lg:top-20">
        <p className="border-b border-paper-200 px-4 py-2.5 text-xs tabular-nums text-ink-400">
          {t('reader.chapterCount', { count: chapters?.length ?? 0 })}
        </p>

        <ul className="max-h-96 overflow-y-auto p-1.5 lg:max-h-sidebar">
          {chapters?.map((ch, i) => {
            const selected = chapterId === ch.chapter_id
            return (
              <li key={ch.chapter_id} className="animate-fade-up" style={delayStyle(i, 12, 240)}>
                <button
                  type="button"
                  onClick={() => onPick(ch.chapter_id)}
                  aria-current={selected ? 'true' : undefined}
                  title={ch.title}
                  className={`group relative w-full truncate rounded-lg py-2 pl-4 pr-3 text-left text-sm transition-colors duration-quick ease-swift ${
                    selected
                      ? 'bg-cinnabar-500 font-medium text-paper-50'
                      : 'text-ink-600 hover:bg-paper-200 hover:text-ink-900'
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className={`absolute inset-y-1 left-1 w-0.5 origin-center rounded-full bg-paper-50 transition-transform duration-calm ease-spring ${
                      selected ? 'scale-y-100' : 'scale-y-0'
                    }`}
                  />
                  {ch.title}
                </button>
              </li>
            )
          })}

          {error && <li className="px-3 py-2 text-sm text-cinnabar-600">{error}</li>}
          {!chapters?.length && !error && (
            <li className="px-3 py-2 text-sm text-ink-400">{t('reader.noChapters')}</li>
          )}
        </ul>
      </div>
    </nav>
  )
}

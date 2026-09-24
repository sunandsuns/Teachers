import { Button } from '../../components/ui'
import { ErrorBox, Loading } from '../../components/Status'
import type { SourceReader } from './useSourceReader'
import { useI18n } from '../../i18n'

/**
 * 原典正文。
 *
 * 单独居中成栏（`max-w-3xl`）：满宽会让一行排到六十余字，中文长文读起来很累，
 * 视线从行尾折回行首时容易串行。
 *
 * 比原来多了一条**细进度条**。《资治通鉴》三百余万字，光靠"已载入 6 / 3,216,638 字"
 * 这行数字，用户感觉不出自己走了多远；一条 2px 的横线能一眼看出"这才刚开头"。
 * 进度用 `scaleX` 而不是 `width` 驱动，动画留在合成层。
 */
export default function SourceView({
  source,
  paginated,
  loaded,
}: {
  source: SourceReader
  paginated: boolean
  loaded: number
}) {
  const { t } = useI18n()
  const percent = source.total > 0 ? (loaded / source.total) * 100 : 0

  return (
    <article className="card mx-auto w-full max-w-3xl p-6 sm:p-8">
      {source.loading && !source.text && <Loading text={t('reader.loadingSource')} />}
      {source.error && <ErrorBox message={source.error} />}

      {source.text && (
        <>
          {/* 从「寻章」跳进来时（offset > 0）必须交代一句"你不是从头读的"，
              否则用户会以为这本书的开头丢了 */}
          {source.startOffset > 0 && (
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-paper-300 bg-paper-100 px-4 py-2.5 text-sm text-ink-600 animate-drop-in">
              <span>{t('reader.startAt', { offset: source.startOffset.toLocaleString() })}</span>
              <Button variant="secondary" size="sm" onClick={source.restart}>
                {t('reader.fromStart')}
              </Button>
            </div>
          )}

          <pre className="whitespace-pre-wrap font-serif text-base leading-loose text-ink-800">
            {source.text}
          </pre>

          {paginated && (
            <div className="mt-8 border-t border-paper-200 pt-4">
              <div
                aria-hidden="true"
                className="mb-3 h-0.5 w-full overflow-hidden rounded-full bg-paper-200"
              >
                <span
                  className="block h-full origin-left rounded-full bg-cinnabar-400 transition-transform duration-slow ease-spring"
                  style={{ transform: `scaleX(${percent / 100})` }}
                />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 text-sm tabular-nums text-ink-500">
                <span>
                  {t('reader.progress', {
                    loaded: loaded.toLocaleString(),
                    total: source.total.toLocaleString(),
                  })}
                </span>
                {source.hasMore && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={source.loadMore}
                    disabled={source.loading}
                    loading={source.loading}
                  >
                    {source.loading ? t('reader.loading') : t('reader.loadMore')}
                  </Button>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </article>
  )
}

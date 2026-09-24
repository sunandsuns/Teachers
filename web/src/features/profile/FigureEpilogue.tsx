import type { FigureInfo } from '../../api/client'
import { Button } from '../../components/ui'
import { useI18n } from '../../i18n'

/**
 * 题跋：像在哪里。
 *
 * 放在整个舞台**下面**而不是挤进中间那一栏——理由要两三句话才说得清，
 * 画框边上那点宽度写不下。排版用楷体长行距，读起来像一段跋文而不是一段说明。
 *
 * 「名录空着」与「还没评出来」是两件事，所以分成两句说：
 * 前者是"这一册里没有人"（没什么可做的），后者是"还没到评的时候"。
 */
export default function FigureEpilogue({
  chosen,
  poolSize,
  busy,
  onEvaluate,
}: {
  chosen: FigureInfo | null
  poolSize: number
  busy: boolean
  onEvaluate: () => void
}) {
  const { t } = useI18n()

  return (
    <>
      {chosen && (
        <section className="mx-auto mt-10 max-w-2xl text-center animate-fade-up">
          {chosen.reason && (
            <>
              <h3 className="font-serif text-sm font-bold tracking-[0.22em] text-cinnabar-600">
                {t('profile.figure.reason')}
              </h3>
              <p className="mt-3 font-serif text-[0.9375rem] leading-loose text-ink-800">
                {chosen.reason}
              </p>
            </>
          )}

          <p className="mt-3 text-xs tabular-nums text-ink-400">
            {t('profile.figure.meta', { date: chosen.chosen_at, count: chosen.pool_size })}
          </p>

          <div className="mt-4">
            <Button variant="ghost" size="sm" onClick={onEvaluate} disabled={busy}>
              {busy ? t('profile.figure.evaluating') : t('profile.figure.evaluate')}
            </Button>
          </div>
        </section>
      )}

      {/* 名录空着时说一句，而不是让页面永远停在册页上让人以为没做完 */}
      {!chosen && poolSize === 0 && (
        <p className="mt-6 text-center text-xs text-ink-400">{t('profile.figure.none')}</p>
      )}
    </>
  )
}

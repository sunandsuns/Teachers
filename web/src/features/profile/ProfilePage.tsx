import { Button, ConfirmBar, Empty, PageHeader, Segmented, Spinner } from '../../components/ui'
import { ErrorBox, Loading } from '../../components/Status'
import { useI18n } from '../../i18n'
import FigureEpilogue from './FigureEpilogue'
import ProfileStage from './ProfileStage'
import { useLeadLines } from './useLeadLines'
import { useProfile } from './useProfile'

/**
 * 画像：从你自己问过的话里，慢慢拼出的"你是谁"。
 *
 * 编排层只做三件事：把 hook 的状态摊给子组件、把子组件的回调接回 hook、
 * 决定"此刻该显示哪一块"。三条行为契约都在 `useProfile` 里，这里只负责版面。
 *
 * 版面的次序：
 *   **页头（清空 / 重新归纳）→ 确认条 → 工具栏（男女 / 总数）→ 状态话 →
 *    舞台（形象居中、特征挂两侧）→ 题跋（像在哪里）→ 脚注**
 *
 * 确认条紧贴页头，与触发它的那个按钮同屏——删到一半的询问飘到页面另一头，
 * 用户会找不到自己在确认什么。
 */
export default function ProfilePage() {
  const { lang, t } = useI18n()
  const {
    data,
    loading,
    error,
    busy,
    note,
    confirmingClear,
    unavailable,
    avatar,
    figure,
    chosen,
    grouped,
    columns,
    runExtract,
    runFigure,
    pickAvatar,
    removeTrait,
    askClear,
    doClearAll,
    cancelClear,
  } = useProfile()

  const { stageRef, figureRef, columnRefs, cardRefs, lines } = useLeadLines(columns, lang, avatar)

  return (
    <section className="mx-auto w-full max-w-5xl">
      <PageHeader title={t('profile.title')} description={t('profile.description')}>
        {data !== null && data.total > 0 && (
          <Button
            variant="secondary"
            size="sm"
            onClick={askClear}
            disabled={confirmingClear || busy}
          >
            {t('profile.clear')}
          </Button>
        )}
        <Button size="sm" onClick={() => void runExtract()} disabled={busy || confirmingClear}>
          {busy ? t('profile.extracting') : t('profile.extract')}
        </Button>
      </PageHeader>

      {/* 清空不可撤销，问一句再动手 */}
      {confirmingClear && (
        <ConfirmBar
          message={t('profile.confirmClear')}
          confirmLabel={t('common.confirmDelete')}
          busyLabel={t('common.deleting')}
          cancelLabel={t('common.cancel')}
          busy={busy}
          onConfirm={() => void doClearAll()}
          onCancel={cancelClear}
        />
      )}

      {unavailable && <ErrorBox message={t('profile.unavailable', { error: data?.error ?? '' })} />}

      {loading && <Loading text={t('profile.loading')} />}
      {error && <ErrorBox message={error} />}

      {!loading && !unavailable && (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2">
            <Segmented
              value={avatar}
              ariaLabel={t('profile.avatarGroup')}
              onChange={value => void pickAvatar(value)}
              options={[
                { value: 'male' as const, label: t('profile.avatar.male') },
                { value: 'female' as const, label: t('profile.avatar.female') },
              ]}
            />
            <p className="text-sm tabular-nums text-ink-500">
              {t('profile.total', { count: data?.total ?? 0 })}
              {data !== null && data.pending > 0 && (
                <>
                  <span aria-hidden="true" className="mx-2 text-paper-400">
                    ·
                  </span>
                  {t('profile.pending', { count: data.pending })}
                </>
              )}
            </p>
          </div>

          {/* 状态话：正在归纳 / 这次新增了几条 / 正在评定。
              在飞时配一个转圈——模型要走几十秒，没有动静的页面会让人以为卡住了 */}
          {note && (
            <p className="mb-5 flex items-center gap-2 text-sm text-ink-500" role="status">
              {busy && <Spinner size="sm" />}
              {note}
            </p>
          )}

          <ProfileStage
            columns={columns}
            avatar={avatar}
            chosen={chosen}
            onDelete={removeTrait}
            stageRef={stageRef}
            figureRef={figureRef}
            columnRefs={columnRefs}
            cardRefs={cardRefs}
            lines={lines}
          />

          {grouped.length === 0 && (
            <div className="mt-2">
              <Empty
                title={t('profile.empty')}
                hint={t('profile.emptyHint')}
                icon={
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className="h-5 w-5"
                  >
                    <path d="M10 2a5 5 0 100 10 5 5 0 000-10zM4 18a6 6 0 0112 0H4z" />
                  </svg>
                }
              />
            </div>
          )}

          <FigureEpilogue
            chosen={chosen}
            poolSize={figure.pool_size}
            busy={busy}
            onEvaluate={() => void runFigure()}
          />

          {grouped.length > 0 && (
            <p className="mt-8 text-center text-xs text-ink-400">{t('profile.footnote')}</p>
          )}
        </>
      )}
    </section>
  )
}

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { HistoryItem, TopicItem } from '../../api/client'
import { ErrorBox } from '../../components/Status'
import { Button, ConfirmBar, Empty, PageHeader, Reveal, Skeleton } from '../../components/ui'
import { useI18n } from '../../i18n'
import SelectionBar from './SelectionBar'
import StatusLine from './StatusLine'
import TopicCard from './TopicCard'
import { useHistoryStore } from './useHistoryStore'
import { useSelection } from './useSelection'

/** 要先问一句再动手的删除动作。
 *
 * 刻意只存"要做哪件事"，不存目标清单：真正执行时按**当时**的勾选去算，
 * 免得在确认条上停留的那几秒里，数据已经和弹出来时不是一回事了。 */
type PendingAction =
  | { kind: 'selected' }
  | { kind: 'topic'; topic: TopicItem }
  | { kind: 'all' }

/** 载入态用骨架屏：列表的版式是已知的，先把卡片撑出来，数据到了不跳版。 */
function TopicListSkeleton() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="card p-5">
          <div className="flex items-start justify-between gap-4">
            <Skeleton className="h-5 w-56" />
            <Skeleton className="h-3.5 w-14" />
          </div>
          <Skeleton className="mt-3 h-3.5 w-full" />
          <Skeleton className="mt-2 h-3.5 w-3/5" />
          <Skeleton className="mt-4 h-3 w-24" />
        </div>
      ))}
    </div>
  )
}

/** 空态上的一枚「回响」图标。纯装饰，读屏靠文案。 */
function EchoIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
      <path
        d="M4 6.5A2.5 2.5 0 016.5 4h11A2.5 2.5 0 0120 6.5v6a2.5 2.5 0 01-2.5 2.5H9l-4 4v-4H6.5A2.5 2.5 0 014 12.5v-6z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * 「回响」——求教留下的记录。
 *
 * 这个文件只做**编排**：什么时候摆确认条、什么时候摆选择栏、按什么顺序排。
 * 数据在 `useHistoryStore`，勾选在 `useSelection`，卡片在 `TopicCard`，
 * 概况在 `StatusLine`。所以"删完怎么同步"和"卡片长什么样"是两件互不打扰的事。
 *
 * 页面上只留两处自己的状态：待确认的动作、以及删除请求是否在飞。
 * 它们既不属于服务端数据，也不属于勾选——它们是"用户此刻正在做的一件事"。
 */
export default function HistoryPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const store = useHistoryStore()
  const selection = useSelection(store.generation, store.topics, store.records)

  const [pending, setPending] = useState<PendingAction | null>(null)
  //: 删除请求在飞。按钮要禁掉，免得手快连点两次
  const [busy, setBusy] = useState(false)

  const unavailable = store.status !== null && !store.status.available

  /** 确认条上那句话。数量在这里现算——`pending` 里只存"要删什么"。 */
  function describePending(action: PendingAction): string {
    if (action.kind === 'selected') {
      return t('history.confirmDeleteSelected', { count: selection.pickedCount })
    }
    if (action.kind === 'topic') {
      return t('history.confirmDeleteTopic', { count: action.topic.question_count })
    }
    return t('history.confirmClear')
  }

  /** 勾选删除：先把确认条摆出来，真正动手在 `confirmPending` 里。 */
  function removeSelected() {
    if (selection.pickedCount === 0) {
      // 一个都没勾就点，也得给句话：静默地什么都不发生，最容易被当成"按钮坏了"
      store.setNote(t('history.nothingPicked'))
      return
    }
    setPending({ kind: 'selected' })
  }

  /** 确认条上按了「确认删除」：这才真正动手。 */
  async function confirmPending() {
    const action = pending
    if (!action) return
    setBusy(true)
    try {
      if (action.kind === 'selected') {
        const deleted = await store.deleteSelected(
          [...selection.pickedTopics],
          [...selection.pickedRecords],
        )
        // 删了多少以服务端返回的为准，不自己猜。
        // 注意这句要排在 deleteSelected 之后：它内部的 load 开头会把上一条提示清掉。
        if (deleted !== null) {
          store.setNote(t('history.deletedSelected', { count: deleted }))
        }
      } else if (action.kind === 'topic') {
        await store.deleteTopic(action.topic)
      } else {
        await store.clearAll()
      }
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  /** 接着问同一个问题，并带上所属话题——新问题才归得回这件事。 */
  function askAgain(topicId: string, record: HistoryItem) {
    navigate(
      `/ask?q=${encodeURIComponent(record.question)}` + `&topic=${encodeURIComponent(topicId)}`,
    )
  }

  return (
    <section className="mx-auto w-full max-w-3xl">
      <PageHeader title={t('history.title')} description={t('history.description')}>
        {store.topicTotal > 0 && (
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                selection.selecting ? selection.dropSelection() : selection.setSelecting(true)
              }
              disabled={busy || pending !== null}
            >
              {selection.selecting ? t('history.exitSelect') : t('history.select')}
            </Button>
            {/* 选择模式下把「清空」收起来：清空是"全都要删"，
                与"挑几条删"是两种相反的心智，并排摆着容易点错 */}
            {!selection.selecting && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setPending({ kind: 'all' })}
                disabled={busy || pending !== null}
              >
                {t('history.clear')}
              </Button>
            )}
          </>
        )}
      </PageHeader>

      {/* 确认条摆在最上面，并把选择栏顶掉——两处都报数只会互相打架。
          卡片上的勾选框留着：确认条上的数字是渲染时现算的，改勾选它立刻跟着变，
          用户点头时看到的数就是真会删掉的数 */}
      {pending && (
        <ConfirmBar
          message={describePending(pending)}
          confirmLabel={t('common.confirmDelete')}
          busyLabel={t('common.deleting')}
          cancelLabel={t('common.cancel')}
          busy={busy}
          onConfirm={() => void confirmPending()}
          onCancel={() => setPending(null)}
        />
      )}

      {selection.selecting && !pending && (
        <SelectionBar
          pickedTopics={selection.pickedTopics.size}
          pickedRecords={selection.pickedRecords.size}
          pickedCount={selection.pickedCount}
          allPicked={selection.allPicked}
          busy={busy}
          onToggleAll={selection.toggleSelectAll}
          onDelete={removeSelected}
        />
      )}

      {store.status && <StatusLine status={store.status} />}

      {/* 库不可用不是"空"，也不是崩溃：照常渲染、说明原因，
          并讲清影响范围——否则用户会以为整个应用坏了 */}
      {unavailable && (
        <ErrorBox message={t('history.unavailable', { error: store.status?.error ?? '' })} />
      )}

      {store.loading && (
        <div role="status" aria-busy="true">
          <span className="sr-only">{t('history.loading')}</span>
          <TopicListSkeleton />
        </div>
      )}

      {store.error && <ErrorBox message={store.error} />}

      {/* 删除结果用轻提示，不弹红框：删干净了是好事，不是故障 */}
      {store.note && <p className="mb-4 text-sm text-ink-500">{store.note}</p>}

      {!store.loading && !unavailable && store.topics.length === 0 && (
        <Empty icon={<EchoIcon />} title={t('history.empty')} />
      )}

      <div className="space-y-4">
        {store.topics.map((topic, i) => (
          <Reveal key={topic.id} index={i}>
            <TopicCard
              topic={topic}
              records={store.records[topic.id] ?? []}
              open={store.openTopic === topic.id}
              opening={store.opening === topic.id}
              selecting={selection.selecting}
              topicPicked={selection.pickedTopics.has(topic.id)}
              pickedRecords={selection.pickedRecords}
              onToggle={() => void store.toggleTopic(topic)}
              onPickTopic={() => selection.pickTopic(topic.id)}
              onPickRecord={selection.pickRecord}
              onAskAgain={record => askAgain(topic.id, record)}
              onDeleteRecord={id => void store.removeRecord(topic.id, id)}
              onDeleteTopic={() => setPending({ kind: 'topic', topic })}
            />
          </Reveal>
        ))}
      </div>

      {store.topics.length < store.topicTotal && (
        <div className="flex justify-center pt-6">
          <Button variant="secondary" onClick={() => void store.loadMore()} disabled={store.more}>
            {store.more
              ? t('history.loadMoreBusy')
              : t('history.loadMore', { count: store.topicTotal - store.topics.length })}
          </Button>
        </div>
      )}
    </section>
  )
}

import type { ReactNode } from 'react'
import { api } from '../../api/client'
import { Badge, Button, Card } from '../../components/ui'
import { ErrorBox, Loading } from '../../components/Status'
import { useAsync } from '../../hooks/useAsync'
import { useI18n } from '../../i18n'
import type { MessageKey } from '../../i18n'
import { shortTime } from './constants'

/** 阅读状态 → 文案。认不出的值原样显示：库里多出一个状态时，这一页不该崩。 */
const STATUS_KEY: Record<string, MessageKey> = {
  wish: 'shelf.status.wish',
  reading: 'shelf.status.reading',
  done: 'shelf.status.done',
}

/** 可见性 → 文案。`pending` / `rejected` 是这个页面最该看清的两个。 */
const VISIBILITY_KEY: Record<string, MessageKey> = {
  private: 'shelf.visibility.private',
  pending: 'shelf.visibility.pending',
  public: 'shelf.visibility.public',
  rejected: 'shelf.visibility.rejected',
}

/**
 * 单个用户的详情。**就地展开，不弹窗**——嵌入式预览里原生弹窗会被静默拦掉
 * （同 `UsersPanel` 的重置密码表单）。
 *
 * 数据在这里自己拉，不从 `AdminPage` 那三个 `useAsync` 里挤：那三个是
 * "所有用户"的量级，而详情是"某一个人"的量级，混在一起会让每次切页签都
 * 顺带查一遍没人在看的用户详情。
 *
 * 五块内容的顺序按"管理员点进来想知道什么"排：**先知道这是谁、他有多少东西，
 * 再看他具体干了什么**。问答与书架都是截断过的（总数在统计那一排里），
 * 截断了就说清楚截断了——只列 20 条却不吭声，会让人以为他就问过 20 次。
 */
export default function UserDetailPanel({
  userId,
  onClose,
}: {
  userId: number
  onClose: () => void
}) {
  const { t } = useI18n()
  const { data, error, loading } = useAsync(() => api.adminUserDetail(userId), [userId])

  const status = (value: string) => (STATUS_KEY[value] ? t(STATUS_KEY[value]) : value)
  const visibility = (value: string) => (VISIBILITY_KEY[value] ? t(VISIBILITY_KEY[value]) : value)

  return (
    <Card className="space-y-4 p-4">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm text-ink-800">{data?.user.email ?? `#${userId}`}</p>
          <p className="mt-0.5 text-xs text-ink-400">
            {data
              ? [
                  data.user.name,
                  t('admin.registeredAt', { time: shortTime(data.user.created_at) }),
                ]
                  .filter(Boolean)
                  .join(' · ')
              : ''}
          </p>
        </div>
        {data?.user.is_admin && <Badge tone="brand">{t('admin.stat.admins')}</Badge>}
        <Button size="sm" variant="ghost" onClick={onClose}>
          {t('admin.detailClose')}
        </Button>
      </div>

      {loading && <Loading />}
      {!loading && error && <ErrorBox message={error} />}

      {!loading && !error && data && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Mini label={t('admin.stat.history')} value={data.stats.history} />
            <Mini label={t('admin.stat.shelf')} value={data.stats.shelf_books} />
            <Mini label={t('admin.stat.traits')} value={data.stats.traits} />
            <Mini label={t('admin.stat.public')} value={data.stats.public_books} />
          </div>

          <section>
            <SectionTitle>
              {t('admin.detailHistory')}
              {data.stats.history > data.history.length &&
                ` · ${t('admin.detailTruncated', {
                  total: data.stats.history,
                  shown: data.history.length,
                })}`}
            </SectionTitle>
            {data.history.length === 0 ? (
              <Hint>{t('admin.detailHistoryEmpty')}</Hint>
            ) : (
              <ul className="space-y-3">
                {data.history.map(item => (
                  <li key={item.id}>
                    <p className="text-sm text-ink-800">{item.question}</p>
                    <p className="mt-0.5 text-xs text-ink-400">
                      {[
                        shortTime(item.created_at),
                        // 空模型名 = 这次没走到模型，是本地检索降级。如实说，
                        // 别让它显示成一片空白——那看着像数据缺了一块。
                        item.model || t('admin.detailLocalFallback'),
                        t('admin.retrievedCount', { count: item.retrieved_count }),
                      ].join(' · ')}
                    </p>
                    {item.answer && (
                      // 回答动辄上千字，全铺开会把列表撑到没法看。默认收起，
                      // 要深究的人自己点开。
                      <details className="mt-1">
                        <summary className="cursor-pointer text-xs text-ink-400 transition-colors duration-quick hover:text-ink-600">
                          {t('admin.detailShowAnswer')}
                        </summary>
                        <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-ink-600">
                          {item.answer}
                        </p>
                      </details>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <SectionTitle>
              {t('admin.detailBooks')}
              {data.stats.shelf_books > data.books.length &&
                ` · ${t('admin.detailTruncated', {
                  total: data.stats.shelf_books,
                  shown: data.books.length,
                })}`}
            </SectionTitle>
            {data.books.length === 0 ? (
              <Hint>{t('admin.detailBooksEmpty')}</Hint>
            ) : (
              <ul className="space-y-2">
                {data.books.map(book => (
                  <li key={book.id} className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-sm text-ink-800">{book.title}</span>
                    {book.author && <span className="text-xs text-ink-400">{book.author}</span>}
                    {book.year && <span className="text-xs text-ink-300">{book.year}</span>}
                    <Badge tone="neutral">{status(book.status)}</Badge>
                    {/* 待审与已驳回单独着色：这两行是管理员可能要处理的事，
                        和其他书混在一个颜色里就得逐条读过去才发现 */}
                    <Badge tone={book.visibility === 'public' ? 'celadon' : 'neutral'}>
                      {visibility(book.visibility)}
                    </Badge>
                    {book.review_note && (
                      <span className="text-xs text-ink-400">{book.review_note}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <SectionTitle>{t('admin.detailTraits')}</SectionTitle>
            {data.traits.length === 0 ? (
              <Hint>{t('admin.detailTraitsEmpty')}</Hint>
            ) : (
              <ul className="space-y-2">
                {data.traits.map(trait => (
                  <li key={trait.id}>
                    <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <Badge tone="neutral">{trait.category}</Badge>
                      <span className="text-sm text-ink-800">{trait.content}</span>
                      <span className="text-xs tabular-nums text-ink-400">
                        {Math.round(trait.confidence * 100)}%
                      </span>
                    </p>
                    {trait.evidence && (
                      <p className="mt-0.5 text-xs text-ink-400">
                        {t('admin.detailEvidence', { text: trait.evidence })}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </Card>
  )
}

function Mini({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-paper-300 bg-paper-50 px-3 py-2">
      <p className="text-xs text-ink-400">{label}</p>
      <p className="font-serif text-lg font-bold tabular-nums text-ink-900">{value}</p>
    </div>
  )
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <h3 className="mb-2 text-sm font-medium text-ink-700">{children}</h3>
}

/** 空状态。四块内容各自的空都要有话说，不能留一片白。 */
function Hint({ children }: { children: ReactNode }) {
  return <p className="text-xs text-ink-400">{children}</p>
}

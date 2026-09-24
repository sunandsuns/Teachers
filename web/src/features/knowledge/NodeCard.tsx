import type { KbNode } from '../../api/client'
import { Badge, Button } from '../../components/ui'
import { bookTitle, categoryName, useI18n } from '../../i18n'
import { nodeLabel } from './constants'

/**
 * 节点卡片：图右边那一栏的主角。
 *
 * 三件事按重要性排下来：
 *   1. **叫什么、是什么**（标题 + 类型徽章）
 *   2. **它的元信息**（书：作者/类目/章数/有无原典；章节：所属书）
 *   3. **能去哪**（去阅读 / 打开这一章 + 返回全图）
 *
 * 「返回全图」始终在，而且与"再点一次同一个节点"等价——手上不用挪位置。
 */
export default function NodeCard({
  node,
  onOpen,
  onBack,
}: {
  node: KbNode
  onOpen: (node: KbNode) => void
  onBack: () => void
}) {
  const { lang, t } = useI18n()
  const isBook = node.kind === 'book'
  const isTheme = node.kind === 'theme'

  return (
    <div className="card p-4 animate-drop-in">
      <div className="mb-2 flex items-start justify-between gap-3">
        <h2 className="font-serif text-lg font-bold leading-snug text-balance text-ink-900">
          {nodeLabel(node, lang)}
        </h2>
        <Badge tone={isTheme ? 'brand' : isBook ? 'ink' : 'neutral'}>
          {isTheme ? t('kb.legend.theme') : isBook ? t('kb.legend.book') : t('kb.legend.chapter')}
        </Badge>
      </div>

      <dl className="space-y-1 text-xs text-ink-500">
        {isBook && (
          <>
            <MetaRow label={t('kb.meta.author')} value={node.meta.author ?? ''} />
            <MetaRow
              label={t('kb.meta.category')}
              value={node.meta.category ? categoryName(node.meta.category, lang) : ''}
            />
            <MetaRow
              label={t('kb.meta.chapters')}
              value={node.meta.chapter_count !== undefined ? `${node.meta.chapter_count}` : ''}
            />
            <MetaRow
              label={t('kb.meta.source')}
              value={node.meta.has_source ? t('kb.meta.hasSource') : t('kb.meta.noSource')}
            />
          </>
        )}
        {node.kind === 'chapter' && node.meta.book_title && (
          <MetaRow label={t('kb.legend.book')} value={bookTitle(node.meta.book_title, lang)} />
        )}
        <MetaRow label="" value={t('kb.meta.degree', { count: node.degree })} />
      </dl>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {(isBook || node.kind === 'chapter') && (
          <Button size="sm" onClick={() => onOpen(node)}>
            {node.kind === 'chapter' ? t('kb.openChapter') : t('kb.read')}
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onBack}>
          {t('kb.backToFull')}
        </Button>
      </div>
    </div>
  )
}

/** 一行元信息。没有值就整行不渲染——留一个空的"作者："比不显示更难看。 */
function MetaRow({ label, value }: { label: string; value: string }) {
  if (!value) return null
  return (
    <div className="flex gap-2">
      {label && <dt className="shrink-0 text-ink-400">{label}</dt>}
      <dd className="min-w-0 text-ink-600">{value}</dd>
    </div>
  )
}

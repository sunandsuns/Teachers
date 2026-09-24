import { Chip, PageHeader, Segmented } from '../../components/ui'
import { ErrorBox, Loading } from '../../components/Status'
import { useI18n } from '../../i18n'
import GraphCanvas from './GraphCanvas'
import Legend from './Legend'
import LinkList from './LinkList'
import NodeCard from './NodeCard'
import SearchBox from './SearchBox'
import ThemeRows from './ThemeRows'
import CrossRefList from './CrossRefList'
import { statNumber, type Scope } from './constants'
import { useKnowledgeGraph } from './useKnowledgeGraph'

/**
 * 知识库：把全部经典画成一张关系图，点一个节点看它的双链。
 *
 * 编排层只做三件事：把 hook 的状态摊给子组件、把子组件的回调接回 hook、
 * 决定"此刻该显示哪一块"。
 *
 * 版面是「图 + 侧栏」两栏。侧栏的次序是有讲究的：
 *   **搜索 → 当前节点 → 出链 → 反链 → 主题明细 → 互参原文**
 * 从"我要找谁"到"它是什么"再到"它连着什么"，最后才是展开的细节。
 */
export default function KnowledgePage() {
  const { t } = useI18n()
  const {
    scope,
    setScope,
    chapters,
    toggleChapters,
    focus,
    setFocus,
    hover,
    setHover,
    selectNode,
    openNode,
    fullGraph,
    fullError,
    loading,
    detail,
    focusFailed,
    focusLoading,
    visible,
    positions,
    highlight,
    focusedNode,
    labelled,
  } = useKnowledgeGraph()

  return (
    <div>
      <PageHeader
        title={t('kb.title')}
        description={t('kb.description', {
          books: statNumber(fullGraph, 'books'),
          themes: statNumber(fullGraph, 'themes'),
          edges: statNumber(fullGraph, 'edges'),
        })}
      />

      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-3">
        <Segmented<Scope>
          value={scope}
          onChange={setScope}
          ariaLabel={t('kb.scopeGroup')}
          options={[
            { value: 'all', label: t('kb.scope.all') },
            { value: 'book', label: t('kb.scope.book') },
          ]}
        />
        <Chip active={chapters} onClick={toggleChapters} title={t('kb.chaptersHint')}>
          {t('kb.chapters')}
        </Chip>
        <Legend />
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <GraphCanvas
          visible={visible}
          positions={positions}
          highlight={highlight}
          hover={hover}
          focus={focus}
          labelled={labelled}
          loading={loading}
          error={fullError}
          onSelect={selectNode}
          onHover={setHover}
        />

        <aside className="space-y-4">
          <SearchBox onPick={selectNode} />

          {!focus && (
            <div className="card p-4">
              <p className="font-serif text-sm leading-relaxed text-ink-500">{t('kb.pickHint')}</p>
            </div>
          )}

          {focus && focusLoading && <Loading />}
          {focus && focusFailed && <ErrorBox message={t('kb.loadFailed')} />}

          {focus && focusedNode && (
            <>
              <NodeCard node={focusedNode} onOpen={openNode} onBack={() => setFocus(null)} />
              <LinkList
                title={t('kb.link.outgoing')}
                empty={t('kb.link.noneOutgoing')}
                links={detail?.outgoing ?? []}
                onPick={selectNode}
                activeId={hover}
                onHover={setHover}
              />
              <LinkList
                title={t('kb.link.backlinks')}
                empty={t('kb.link.noneBacklinks')}
                links={detail?.backlinks ?? []}
                onPick={selectNode}
                activeId={hover}
                onHover={setHover}
              />
              {detail && detail.theme_rows.length > 0 && <ThemeRows detail={detail} />}
              {detail && detail.cross_refs.length > 0 && <CrossRefList detail={detail} />}
            </>
          )}
        </aside>
      </div>
    </div>
  )
}

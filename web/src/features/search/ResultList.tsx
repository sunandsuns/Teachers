import { Link } from 'react-router-dom'
import type { SearchResultItem } from '../../api/client'
import { Badge, Reveal } from '../../components/ui'
import { sourceLabel, useI18n } from '../../i18n'

/** 结果深链：笔记跳到具体章节，原典跳到原典页并定位到那一段。
 *
 * 两种命中落到两种参数上，所以**不能**合成一个通用链接——
 * 笔记没有 `offset`，原典没有 `chapter_id`。
 *
 * 私人书架那一路（`shelf`）的 `book_id` 是 `shelf-<书架行号>`，在阅读器里
 * 根本不存在这本书。它该回「我的书架」——那才是这本书真正待着的地方。 */
function resultLink(result: SearchResultItem): string {
  if (result.kind === 'shelf') return '/shelf'
  if (result.kind === 'source') {
    return `/books/${result.book_id}?tab=source&offset=${result.offset}`
  }
  return `/books/${result.book_id}?chapter=${encodeURIComponent(result.chapter_id)}`
}

/** 来源标记的色调：原典最沉（墨）、笔记次之（朱砂）、我自己的书最轻（青瓷）。 */
const BADGE_TONE: Record<SearchResultItem['kind'], 'ink' | 'brand' | 'celadon'> = {
  source: 'ink',
  notes: 'brand',
  shelf: 'celadon',
}

const BADGE_KEY = {
  source: 'search.badge.source',
  notes: 'search.badge.notes',
  shelf: 'search.badge.shelf',
} as const

/**
 * 命中结果。
 *
 * 每张卡交代三件事，缺一件用户就得点进去才知道是不是自己要找的：
 *   · **是笔记还是原典**（Badge）——两者的可信度与语气完全不同；
 *   · **出自哪一章**（出处）；
 *   · **相关度**——让用户知道"这是最像的几条"而不是"全部都在这里"。
 */
export default function ResultList({ results }: { results: SearchResultItem[] }) {
  const { lang, t } = useI18n()

  return (
    <ol className="space-y-3">
      {results.map((result, i) => (
        <li key={`${result.book_id}-${result.chapter_id}-${result.offset}-${result.score}`}>
          <Reveal index={i} step={35}>
            <Link to={resultLink(result)} className="card-interactive block p-5">
              <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <span className="flex items-center gap-2">
                  <Badge tone={BADGE_TONE[result.kind]}>{t(BADGE_KEY[result.kind])}</Badge>
                  <span className="font-serif text-sm font-bold text-cinnabar-600">
                    {sourceLabel(result.source, lang)}
                  </span>
                </span>
                <span className="shrink-0 text-xs text-ink-400">
                  {t('search.score', { score: result.score.toFixed(3) })}
                </span>
              </div>

              {/* pre-wrap：原文里的换行是内容的一部分，不该被压掉 */}
              <p className="line-clamp-4 whitespace-pre-wrap font-serif text-sm leading-relaxed text-ink-700">
                {result.content}
              </p>
            </Link>
          </Reveal>
        </li>
      ))}
    </ol>
  )
}

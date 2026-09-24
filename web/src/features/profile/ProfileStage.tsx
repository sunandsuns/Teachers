import type { MutableRefObject, Ref } from 'react'
import type { Avatar, FigureInfo, TraitItem } from '../../api/client'
import type { Columns, LeadLine, Side } from './constants'
import CategoryCard from './CategoryCard'
import Figure from './Figure'

/**
 * 舞台：牵引线画在整个舞台上，卡片与形象各自排在三栏里。
 *
 * 线在 DOM 里排在网格**前面**，因此落在卡片之下——只在边缘相接，不会横穿字。
 * 这一点不能反：线一旦盖在卡片上，那些"分类—形象"的对应关系就会变成
 * 一堆划过文字的噪线。
 *
 * 窄屏折成一栏时形象排在最前（`order-first`）：它是这一页的主角，
 * 排在两列卡片下面就很难注意到了。
 */
export default function ProfileStage({
  columns,
  avatar,
  chosen,
  onDelete,
  stageRef,
  figureRef,
  columnRefs,
  cardRefs,
  lines,
}: {
  columns: Columns
  avatar: Avatar
  chosen: FigureInfo | null
  onDelete: (trait: TraitItem) => void
  stageRef: Ref<HTMLDivElement>
  figureRef: Ref<HTMLDivElement>
  columnRefs: MutableRefObject<Record<Side, HTMLDivElement | null>>
  cardRefs: MutableRefObject<Record<string, HTMLElement | null>>
  lines: LeadLine[]
}) {
  const half = columns.left.length

  return (
    <div ref={stageRef} className="relative">
      <svg aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full">
        {lines.map(line => (
          <g key={line.key} className="animate-fade-in">
            <path d={line.d} fill="none" strokeWidth="1.5" className="stroke-cinnabar-300" />
            <circle cx={line.fromX} cy={line.fromY} r="2.5" className="fill-cinnabar-400" />
            <circle cx={line.toX} cy={line.toY} r="3" className="fill-cinnabar-400" />
          </g>
        ))}
      </svg>

      <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        <div
          ref={el => {
            columnRefs.current.left = el
          }}
          className="space-y-4"
        >
          {columns.left.map((group, i) => (
            <CategoryCard
              key={group.category}
              group={group}
              index={i}
              onDelete={onDelete}
              cardRef={el => {
                cardRefs.current[group.category] = el
              }}
            />
          ))}
        </div>

        {/* 窄屏折成一栏时形象排在最前：它是这一页的主角，
            排在两列卡片下面就很难注意到 */}
        <div className="order-first mx-auto w-40 self-start sm:w-48 md:order-none lg:w-60">
          <Figure avatar={avatar} chosen={chosen} boxRef={figureRef} />
        </div>

        <div
          ref={el => {
            columnRefs.current.right = el
          }}
          className="space-y-4"
        >
          {columns.right.map((group, i) => (
            <CategoryCard
              key={group.category}
              group={group}
              index={half + i}
              onDelete={onDelete}
              cardRef={el => {
                cardRefs.current[group.category] = el
              }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

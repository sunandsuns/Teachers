import type { Ref } from 'react'
import type { Avatar, FigureInfo } from '../../api/client'
import { useI18n } from '../../i18n'
import { FIGURES } from './constants'

/**
 * 形象：一页册页，或一位历史人物。
 *
 * 两页册页的差别落在**画本身**——陶渊明是执杖的士人，仕女是低眉回身的女子——
 * 不靠颜色或符号去区分，那样会把"这是谁"变成"这是个什么标签"。
 *
 * ``boxRef`` 只挂在**画框那一层**上（不含题签）：牵引线是量它的边框来定位的，
 * 所以换谁进来都不能改画框的尺寸与位置。
 */
export default function Figure({
  avatar,
  chosen,
  boxRef,
}: {
  avatar: Avatar
  /** 评出来的那一位；还没评出来时是 null，退回册页 */
  chosen: FigureInfo | null
  boxRef: Ref<HTMLDivElement>
}) {
  const { t } = useI18n()
  const leaf = FIGURES[avatar]
  // 时代与一句话凑成题签的第二行；两样都可能缺，缺了就不留一个孤零零的分隔点
  const subtitle = chosen ? [chosen.era, chosen.blurb].filter(Boolean).join(' · ') : ''

  return (
    <figure className="w-full">
      <div
        ref={boxRef}
        className="aspect-portrait w-full overflow-hidden rounded-sm bg-paper-200 shadow-leaf ring-1 ring-paper-300"
      >
        {/* 册页两幅画心的尺寸是写死的，用来提示固有比例；名录里的人尺寸各异，
            交给 `object-contain` 按画框去算 */}
        <img
          // key 随"画的是谁"变：换册页或评出新的人时重挂一次，
          // 让淡入动画重放——否则画面会无声无息地换掉，看不出发生了什么
          key={chosen ? chosen.id : avatar}
          src={chosen ? chosen.portrait : leaf.src}
          alt={chosen ? chosen.name : t('profile.figureAlt')}
          width={chosen ? undefined : leaf.w}
          height={chosen ? undefined : leaf.h}
          className="h-full w-full object-contain animate-fade-in"
        />
      </div>

      <figcaption className="mt-2 text-center text-[0.6875rem] leading-relaxed text-ink-400">
        {chosen ? (
          <>
            <span className="block text-[0.625rem] tracking-[0.22em] text-cinnabar-500">
              {t('profile.figure.picked')}
            </span>
            <span className="mt-1 block font-serif text-lg font-bold tracking-wide text-ink-800">
              {chosen.name}
            </span>
            {subtitle && <span className="mt-0.5 block text-xs text-ink-500">{subtitle}</span>}
            {chosen.credit && <span className="mt-1 block">{chosen.credit}</span>}
          </>
        ) : (
          <>
            {/* 古画不是"素材"，署名与藏地要跟着走 */}
            <span className="block">{t(leaf.credit)}</span>
            <span className="block text-ink-300">{t('profile.figureSource')}</span>
          </>
        )}
      </figcaption>
    </figure>
  )
}

import type { Avatar, ExtractResult, FigureInfo, FigureResult, TraitItem } from '../../api/client'
import type { MessageKey } from '../../i18n'
import figureFemale from '../../assets/figure-female.webp'
import figureMale from '../../assets/figure-male.webp'

/** 够宽才画牵引线：再窄一点三栏就折成一栏了。 */
export const LINES_MIN_WIDTH = 760
/** 牵引线出发的高度范围（占画心高度的比例）。上不过肩、下不过衣摆。 */
export const ANCHOR_TOP = 0.22
export const ANCHOR_BOTTOM = 0.88
/** 出发点从画心边缘再往里收一点，免得圆点压在画框的边上。 */
export const FIGURE_INSET = 0.02

export type Translate = (key: MessageKey, params?: Record<string, string | number>) => string
export type Side = 'left' | 'right'

/** 一条牵引线。坐标都已换算成相对舞台的像素。 */
export interface LeadLine {
  key: string
  d: string
  fromX: number
  fromY: number
  toX: number
  toY: number
}

/** 一个分类下挂着的全部特征。 */
export interface CategoryGroup {
  category: string
  traits: TraitItem[]
}

/** 分类按"前半边在左、后半边在右"分好的两列。 */
export interface Columns {
  left: CategoryGroup[]
  right: CategoryGroup[]
}

/** 归纳失败时后端给的代号 → 人话。不在表里的（上游错误原文）直接显示。 */
export const EXTRACT_CODE_KEYS: Record<string, MessageKey> = {
  no_records: 'profile.err.noRecords',
  llm_disabled: 'profile.err.noLlm',
  nothing_usable: 'profile.err.nothingNew',
}

/** 评定历史人物失败时后端给的代号 → 人话。同样，表外的原文直接显示。 */
export const FIGURE_CODE_KEYS: Record<string, MessageKey> = {
  no_traits: 'profile.err.noTraits',
  no_pool: 'profile.err.noPool',
  not_in_pool: 'profile.err.notInPool',
  llm_disabled: 'profile.err.noLlmFigure',
  history_unavailable: 'profile.err.noStore',
}

/** 「最像你的一位历史人物」的空档：还没评过、名录为空、库不可用都长这样。 */
export const NO_FIGURE: FigureInfo = {
  id: '',
  name: '',
  era: '',
  blurb: '',
  reason: '',
  credit: '',
  portrait: '',
  week: '',
  chosen_at: '',
  pool_size: 0,
  needs_refresh: false,
}

/**
 * 默认形象：两页册页的画心。
 *
 * 两幅画心比例本就不同（陶渊明像略横、仕女图偏竖），所以容器用 `object-contain`：
 * 差额由 `paper-200` 的底色补上，正好当装裱，不必把画硬裁成一个比例。
 *
 * `credit` 是题签式的出处说明。古画不是"素材"，署名与藏地要跟着走——
 * 一是尊重，二是它本身也好看。
 */
export const FIGURES: Record<Avatar, { src: string; w: number; h: number; credit: MessageKey }> = {
  male: { src: figureMale, w: 624, h: 607, credit: 'profile.figureCredit.male' },
  female: { src: figureFemale, w: 624, h: 679, credit: 'profile.figureCredit.female' },
}

/**
 * 一次归纳的结果 → 一句给人看的话。
 *
 * 顺序是刻意的：**先看有没有读出东西**（`extracted > 0`），再看错误码。
 * 反过来的话，模型读出 3 条同时上游报了个警告，用户会只看到警告。
 */
export function describeExtract(result: ExtractResult, t: Translate): string {
  if (result.extracted > 0) return t('profile.extracted', { count: result.extracted })
  const key = EXTRACT_CODE_KEYS[result.error]
  if (key) return t(key)
  // 上游的原始错误（比如 "HTTP 503：…"）比我们的兜底话更有用
  return result.error || t('profile.nothingNew')
}

/** 一次评定的结果 → 一句给人看的话。选出来了不必报名字，
 *  画框里的题签已经写着是谁。 */
export function describeFigure(result: FigureResult, t: Translate): string {
  if (result.ok) return t('profile.figure.done')
  const key = FIGURE_CODE_KEYS[result.error]
  if (key) return t(key)
  return result.error || t('profile.figureFailed')
}

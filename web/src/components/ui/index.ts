/**
 * UI 原子层出口。
 *
 * 这一层**只依赖令牌**（tailwind.config.js + index.css），不 import 任何
 * `api/*`、不读业务文案、不知道"书架"或"回响"是什么。反过来，feature 层
 * 可以放心吃这一层——这就是低耦合的方向性。
 *
 * 用桶文件收口，是为了让 feature 的 import 一眼看出"用了哪些原子"：
 *     import { Button, Card, Empty, Reveal } from '../../components/ui'
 * 而不是五行散落的相对路径。
 */

export { default as Badge } from './Badge'
export { default as Button } from './Button'
export { default as Card, SURFACE, type SurfaceVariant } from './Card'
export { default as Chip } from './Chip'
export { default as Collapse } from './Collapse'
export { default as ConfirmBar } from './ConfirmBar'
export { default as Empty } from './Empty'
export { default as PageHeader } from './PageHeader'
export { default as Reveal } from './Reveal'
export { default as Segmented } from './Segmented'
export { Skeleton, SkeletonText } from './Skeleton'
export { default as Spinner } from './Spinner'

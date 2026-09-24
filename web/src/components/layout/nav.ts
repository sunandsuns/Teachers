import type { MessageKey } from '../../i18n'

/**
 * 导航的数据模型。
 *
 * 抽成纯数据（没有 JSX、不 import 组件）的好处：改导航是改**一张表**，
 * 而不是在 JSX 里增删一段。将来要按权限裁剪、按版本开关，也只需过滤这张表。
 *
 * 分组（`group`）不是装饰：七个入口其实是两类事——
 *   read    「我去看已有的东西」：书架、寻章、知识库
 *   reflect 「我把自己的东西放进去、再从里面看出点什么」：求教、回响、画像、感悟
 * 两组之间放一条发丝线，人扫一眼就知道"左边是资料，右边是我的"。
 * 不写组名文字，是因为七个入口本身已经够挤，加字会喧宾夺主。
 */
export type NavGroup = 'read' | 'reflect'

export interface NavItem {
  to: string
  key: MessageKey
  group: NavGroup
  /** 只在路径完全相等时才算激活。用于 `/`——否则任何路径都会点亮书架。 */
  exact?: boolean
  /** 额外的归属前缀：这些路径下也算作本项激活。
   *  用于 `/books/:bookId`——读者在读书时，顶栏该亮的是「书架」，
   *  而不是整条导航全灭（"我到底在哪儿"是导航最不该让人猜的事）。 */
  also?: readonly string[]
}

export const NAV_ITEMS: readonly NavItem[] = [
  { to: '/', key: 'nav.library', group: 'read', exact: true, also: ['/books'] },
  // 「我的书架」紧跟「书架」：一个是随包发布的公共书目，一个是自己往里加的书，
  // 是同一件事的两面。放在这里而不是"我的"那一组，是因为用户找它时会先想到
  // 「书架」，不会想到「画像」。
  { to: '/shelf', key: 'nav.mine', group: 'read' },
  { to: '/search', key: 'nav.search', group: 'read' },
  // 知识库一直有路由却没有任何入口——用户永远走不到那一页。
  // 补进导航，顺带把它归到"资料"这一组：它确实是书目的另一种看法。
  { to: '/knowledge', key: 'nav.knowledge', group: 'read' },
  { to: '/ask', key: 'nav.ask', group: 'reflect' },
  // 「回响」紧跟「求教」：它存的就是求教留下的记录，两块内容是一体的
  { to: '/history', key: 'nav.history', group: 'reflect' },
  // 「画像」接着「回响」：它归纳的也正是那些记录，是同一批素材的另一种看法
  { to: '/profile', key: 'nav.profile', group: 'reflect' },
  { to: '/insights', key: 'nav.insights', group: 'reflect' },
]

/**
 * 后台入口。**单独一条，不在 `NAV_ITEMS` 里**。
 *
 * 它不是"多一个页面"，而是"多一类人"：只有管理员该看到它。混在主表里、
 * 由顶栏在渲染时按身份过滤也行，但那样"这一项什么时候会出现"就散在两个
 * 文件里了——主表看不出它特殊，顶栏里又多一个 if。分开摆，一眼能看出
 * 这套导航有两种可见性。
 *
 * 归属 `read` 只是为了让滑动指示器与分组线算得对；它排在最后一个，
 * 所以实际显示在最右边。
 */
export const ADMIN_NAV_ITEM: NavItem = { to: '/admin', key: 'nav.admin', group: 'read' }

/** 按身份算出当前该显示哪些导航项。 */
export function navItemsFor(isAdmin: boolean): readonly NavItem[] {
  return isAdmin ? [...NAV_ITEMS, ADMIN_NAV_ITEM] : NAV_ITEMS
}

/** 当前路径是否命中某个导航项。
 *
 *  `/books/01` 这种子路径要能点亮它的父级入口，所以用 `startsWith(to + '/')`
 *  而不是 `startsWith(to)`——后者会让 `/searching` 也点亮 `/search`。 */
export function isNavItemActive(pathname: string, item: NavItem): boolean {
  const matches = (prefix: string) =>
    pathname === prefix || pathname.startsWith(`${prefix}/`)
  if (item.also?.some(matches)) return true
  if (item.exact) return pathname === item.to
  return matches(item.to)
}

/**
 * 页面在"空间"里的次序，用来算转场方向。
 *
 * 就是导航从左到右的排布。用户看到「书架」在最左、「感悟」在右，那么从书架
 * 去感悟就该"往右走"，从感悟回书架就该"往左走"。方向一旦和导航的排布一致，
 * 转场就不再是一层随机特效，而是**位置的移动**——这是它看起来"对"的全部原因。
 *
 * 管理员那一项也排进来：它实际显示在最右，次序得跟着。
 *
 * 返回 `-1` 表示这个路径不在导航上（登录、注册）。它们是"进去一下再出来"的
 * 地方，不是并排的模块，横向没有可比的位置，由调用方降级成纵深转场。
 */
const SPATIAL_ORDER: readonly NavItem[] = [...NAV_ITEMS, ADMIN_NAV_ITEM]

export function pageOrder(pathname: string): number {
  return SPATIAL_ORDER.findIndex(item => isNavItemActive(pathname, item))
}

/**
 * 当前路径**归属**的那个导航项；不在导航上（登录、注册）时返回 `null`。
 *
 * 与 `pageOrder` 同源，都用 `isNavItemActive` 判断归属——"这一页叫什么"
 * 只有一处答案。登录门禁拿它来点名（「寻章」要登录之后才能用），
 * 而不是再维护一张 路径 → 功能名 的表。
 */
export function navItemFor(pathname: string): NavItem | null {
  return SPATIAL_ORDER.find(item => isNavItemActive(pathname, item)) ?? null
}

/** 转场方向。 */
export type TransitionDirection = 'forward' | 'back' | 'depth'

/**
 * 从 `from` 走到 `to`，该往哪个方向演。
 *
 * 三种情形都归到 `depth`（纵深、自下浮起）：
 *   · 有一端不在导航上（进登录页、从登录页回来）；
 *   · 两端是同一个导航项（`/books/01` → `/books/02`）——横向没有位移可言，
 *     而且读者"翻到下一章"的直觉是往下走，不是往旁边走。
 */
export function transitionDirection(from: string, to: string): TransitionDirection {
  const before = pageOrder(from)
  const after = pageOrder(to)
  if (before < 0 || after < 0 || before === after) return 'depth'
  return after > before ? 'forward' : 'back'
}

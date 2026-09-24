import type { MessageKey } from '../../i18n'
import type { ShelfStatus, ShelfVisibility } from '../../api/client'

/**
 * 三种阅读状态。
 *
 * 顺序就是界面上筛选药丸的顺序，也是"从心愿到读完"的自然顺序——
 * 按字母或按后端字典序排都讲不出这个道理。
 */
export const STATUS_ORDER: readonly ShelfStatus[] = ['wish', 'reading', 'done']

export const STATUS_KEY: Record<ShelfStatus, MessageKey> = {
  wish: 'shelf.status.wish',
  reading: 'shelf.status.reading',
  done: 'shelf.status.done',
}

/**
 * 可见性的展示顺序与样式。
 *
 * 颜色是**语义**不是装饰：只有 `public` 用朱砂（"已经在公共书架上了"），
 * `rejected` 用灰（"这件事已经了结"），其余两个保持中性。让用户扫一眼就知道
 * 这本书走到哪一步了。
 */
export const VISIBILITY_ORDER: readonly ShelfVisibility[] = [
  'private',
  'pending',
  'public',
  'rejected',
]

export const VISIBILITY_KEY: Record<ShelfVisibility, MessageKey> = {
  private: 'shelf.visibility.private',
  pending: 'shelf.visibility.pending',
  public: 'shelf.visibility.public',
  rejected: 'shelf.visibility.rejected',
}

export const VISIBILITY_TONE: Record<ShelfVisibility, 'plain' | 'warn' | 'good'> = {
  private: 'plain',
  pending: 'warn',
  public: 'good',
  rejected: 'plain',
}

/** 导读在后台生成，前端隔几秒回来看一眼。 */
export const GUIDE_POLL_MS = 4000
/**
 * 最多看几次。
 *
 * 必须封顶：生成失败时 `has_guide` 会永远是 false，不封顶就是一个永不停止的
 * 轮询。八次约半分钟，够覆盖正常的模型延迟。
 */
export const GUIDE_POLL_MAX = 8

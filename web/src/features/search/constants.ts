import type { MessageKey } from '../../i18n'
import type { SearchKind } from '../../api/client'

/** 一次取多少条结果。12 条大约是一屏半，再多用户也不会看。 */
export const RESULT_LIMIT = 12

/** 示例词固定用中文：检索是在中文语料上做的分词匹配，
 * 换成英文关键词只会得到空结果——与其给一个点了没用的示例，
 * 不如保留中文词，并在输入框提示里说明"要输中文"。 */
export const EXAMPLES = ['自强不息', '知足者富', '不战而屈人之兵', '才者德之资也', '上善若水']

/** 检索范围。四个标签的顺序是"由宽到窄"：先看全部，再收到笔记、原典或我的书架。
 *
 * 「我的书架」放在最后：它是唯一一路**不属于公共语料**的检索，
 * 混在中间会让人以为它和"深读笔记"是一类东西。 */
export const KIND_TABS: readonly { value: SearchKind; key: MessageKey }[] = [
  { value: 'all', key: 'search.kind.all' },
  { value: 'notes', key: 'search.kind.notes' },
  { value: 'source', key: 'search.kind.source' },
  { value: 'shelf', key: 'search.kind.shelf' },
]

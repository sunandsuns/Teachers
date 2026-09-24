import type { Lang } from '../../i18n'

/** 示例问题：**显示**当前语言的问法，**提交**的却始终是那句中文。
 *
 * 检索是在中文语料上做的分词匹配，英文问句几乎命不中任何段落；
 * 而用户点示例图的就是"看看这个例子能得到什么"。所以英文界面下点
 * "How do I face failure?"，实际问的是"如何面对失败和挫折？"，
 * 回答再按当前语言生成——两件事各自用对了语言。
 *
 * 抽成数据而不是写在 JSX 里：将来要按主题轮换、或从后端拉示例，
 * 换掉这个数组就行，组件不用动。
 */
export interface Suggestion {
  zh: string
  en: string
}

export const SUGGESTIONS: readonly Suggestion[] = [
  { zh: '工作中遇到小人怎么办？', en: 'What do I do about a scheming colleague at work?' },
  { zh: '迷茫的时候该怎么选择方向？', en: 'When I feel lost, how should I choose a direction?' },
  { zh: '如何面对失败和挫折？', en: 'How do I face failure and setbacks?' },
  { zh: '怎样才能坚持长期目标？', en: 'How can I keep at a long-term goal?' },
]

/** 按当前界面语言取显示用的问法。提交用的始终是 `zh`。 */
export function suggestionLabel(item: Suggestion, lang: Lang): string {
  return lang === 'en' ? item.en : item.zh
}

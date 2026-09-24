import type { Lang, MessageKey } from '../../i18n'

/** 这一层只做"把数据变成人读得懂的字"，不碰 React、不碰网络。 */
export type Translate = (key: MessageKey, params?: Record<string, string | number>) => string

/** 卡片上那段预览的字符上限。 */
const PREVIEW_LIMIT = 120

const pad = (value: number) => String(value).padStart(2, '0')

/** 时间戳 → "刚刚 / 3 小时前 / 9月14日 20:31"。
 *
 * 历史记录的价值在"这是什么时候问的"，绝对时间戳对人不友好；
 * 超过一周才退回具体日期，那时"几天前"已经算不清了。 */
export function formatTime(ts: number, t: Translate, lang: Lang): string {
  const date = new Date(ts * 1000)
  const elapsed = Date.now() - date.getTime()
  const minute = 60_000
  const hour = 60 * minute
  const day = 24 * hour

  if (elapsed < minute) return t('history.justNow')
  if (elapsed < hour) return t('history.minutesAgo', { count: Math.floor(elapsed / minute) })
  if (elapsed < day) return t('history.hoursAgo', { count: Math.floor(elapsed / hour) })
  if (elapsed < 7 * day) return t('history.daysAgo', { count: Math.floor(elapsed / day) })

  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}`
  if (lang === 'en') {
    // 英文里"Oct 2, 20:31"，月份缩写比"10 月"更自然
    const month = new Intl.DateTimeFormat('en', { month: 'short' }).format(date)
    return `${month} ${date.getDate()}, ${time}`
  }
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日 ${time}`
}

/** ISO 时间 → "9 月 30 日"。用来告诉用户下次什么时候清理。 */
export function formatDay(iso: string | null, t: Translate, lang: Lang): string {
  if (!iso) return t('history.noDate')
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return t('history.noDate')
  if (lang === 'en') {
    return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(date)
  }
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日`
}

/** 回答是整篇 Markdown，卡片上只摊平取开头一小段。
 *
 * 不用 CSS 的多行截断：Markdown 里换行与标记符号都得先压掉，
 * 否则预览第一行可能只有个 `##`。 */
export function preview(text: string): string {
  const flat = text
    .replace(/[#>*`|-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return flat.length > PREVIEW_LIMIT ? `${flat.slice(0, PREVIEW_LIMIT)}…` : flat
}

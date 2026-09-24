import type { KbNodeDetail } from '../../api/client'
import { bookTitle, themeName, useI18n } from '../../i18n'

/**
 * 「在八个主题下」——这本书在每个主题上被归纳出的判断。
 *
 * 书的详情里主题名已经由标题交代，所以只列主题；章节节点才需要带上书名，
 * 否则"· 谋略"这种行会让人不知道是哪本书的判断。
 */
export default function ThemeRows({ detail }: { detail: KbNodeDetail }) {
  const { lang, t } = useI18n()
  const isBook = detail.node.kind === 'book'

  return (
    <div className="card p-4">
      <h3 className="mb-2 text-xs font-medium text-ink-500">{t('kb.themeRows')}</h3>
      <ul className="space-y-2.5">
        {detail.theme_rows.map(row => (
          <li key={`${row.book_id}-${row.theme}`}>
            <p className="text-xs text-ink-400">
              {isBook
                ? themeName(row.theme, lang)
                : `${bookTitle(row.book_title, lang)} · ${themeName(row.theme, lang)}`}
            </p>
            <p className="text-sm leading-relaxed text-ink-700">{row.judgment}</p>
            {row.quote && <p className="mt-0.5 font-kai text-xs text-ink-500">{row.quote}</p>}
          </li>
        ))}
      </ul>
    </div>
  )
}

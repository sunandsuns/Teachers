import { Link } from 'react-router-dom'
import Markdown from '../../components/Markdown'
import { useI18n } from '../../i18n'
import type { Exchange } from './useAdvisor'

/**
 * 一问一答。
 *
 * 问句右对齐、朱砂实底；答句左对齐、纸面留白——不用头像也能一眼分出谁在说话，
 * 而中式的底子上加一个圆头像反而突兀。
 *
 * 底部的出处条是**回答的一部分**，不是装饰：它说明这段答案引用了几段经典、
 * 是模型写的还是本地检索拼的。用户据此判断该信几分。
 */
export default function ExchangeCard({ exchange }: { exchange: Exchange }) {
  const { t } = useI18n()
  const { answer } = exchange

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="flex justify-end">
        {/* pre-wrap：用户自己按下的换行要留住；break-words：长英文不至于撑破气泡 */}
        <div className="max-w-md whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-cinnabar-500 px-4 py-2.5 text-sm leading-relaxed text-paper-50 shadow-card">
          {exchange.question}
        </div>
      </div>

      <div className="card px-5 py-4">
        <Markdown content={answer.answer} />
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-paper-200 pt-3 text-xs text-ink-400">
          <span>{t('ask.cited', { count: answer.retrieved_count })}</span>
          <span aria-hidden="true" className="h-1 w-1 rounded-full bg-paper-400" />
          <span>
            {answer.llm_used
              ? t('ask.aiAnswer', { model: answer.model ?? '' })
              : t('ask.localMode')}
          </span>
          {/* 记录已自动存下，这里给一个去处——不然用户根本不知道有「回响」 */}
          <Link
            to="/history"
            className="ml-auto rounded transition-colors duration-quick hover:text-cinnabar-600"
          >
            {t('ask.saved')}
          </Link>
        </div>
      </div>
    </div>
  )
}

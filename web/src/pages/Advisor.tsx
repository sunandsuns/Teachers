import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type AskResponse } from '../api/client'
import Markdown from '../components/Markdown'
import ModelSettingsPanel from '../components/ModelSettingsPanel'
import { ErrorBox } from '../components/Status'
import Button from '../components/ui/Button'
import Chip from '../components/ui/Chip'
import PageHeader from '../components/ui/PageHeader'
import { useI18n, type Lang } from '../i18n'
import { useModelSettings } from '../hooks/useModelSettings'

interface Exchange {
  question: string
  answer: AskResponse
}

/** 示例问题：**显示**当前语言的问法，**提交**的却始终是那句中文。
 *
 * 检索是在中文语料上做的分词匹配，英文问句几乎命不中任何段落；
 * 而用户点示例图的就是"看看这个例子能得到什么"。所以英文界面下点
 * "How do I face failure?"，实际问的是"如何面对失败和挫折？"，
 * 回答再按当前语言生成——两件事各自用对了语言。 */
const SUGGESTIONS: { zh: string; en: string }[] = [
  { zh: '工作中遇到小人怎么办？', en: 'What do I do about a scheming colleague at work?' },
  { zh: '迷茫的时候该怎么选择方向？', en: 'When I feel lost, how should I choose a direction?' },
  { zh: '如何面对失败和挫折？', en: 'How do I face failure and setbacks?' },
  { zh: '怎样才能坚持长期目标？', en: 'How can I keep at a long-term goal?' },
]

/** 问题长度上限。更长也不是不行，只是检索质量会跟着掉，不如引导用户把话收一收。 */
const MAX_QUESTION_LENGTH = 500

export default function Advisor() {
  const { lang, t } = useI18n()
  // 支持 ?q= 预填：「回响」页的「再问一次」就是这么跳过来的，
  // 让人能接着旧问题追问，而不是重新打一遍字。
  const [params] = useSearchParams()
  const [question, setQuestion] = useState(() => params.get('q') ?? '')
  const [history, setHistory] = useState<Exchange[]>([])
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const { settings, update, payload } = useModelSettings()

  // 输入框跟着内容长高：写到第二行时不会把字挤在一条里横向滚动。
  // 高度只能由内容算出来（静态类表达不了），所以这里直接改 DOM 的 height；
  // 上限交给 max-h-40 + overflow-y-auto（见下方 textarea 的 className）。
  useEffect(() => {
    const el = composerRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [question])

  // 只有"选了自定义且填全了"才会真的换模型。按钮上如实区分三种情况：
  // 选了自定义却还没填时若直接显示"默认"，用户会以为自己白点了那一下。
  const modelLabel =
    settings.mode === 'default'
      ? t('ask.model.default')
      : payload !== null
        ? t('ask.model.custom')
        : t('ask.model.incomplete')

  async function submit(q: string) {
    const trimmed = q.trim()
    if (!trimmed || asking) return
    setAsking(true)
    setError(null)
    try {
      const answer = await api.ask(trimmed, 5, payload, lang)
      setHistory(prev => [...prev, { question: trimmed, answer }])
      setQuestion('')
      requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ask.failed'))
    } finally {
      setAsking(false)
    }
  }

  /** 回车直接发送，Shift + 回车换行。
   *
   * 组词中的回车必须放行——中文输入法里按 Enter 是"选中候选词"，
   * 当成发送就会把半截拼音连同正打的字一起发出去。各浏览器对 isComposing
   * 的置位时机不一致，故一并看 keyCode 229（组词期间固定的键码）。
   */
  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey) return
    if (event.nativeEvent.isComposing || event.keyCode === 229) return
    event.preventDefault()
    void submit(question)
  }

  const suggestionLabel = (item: { zh: string; en: string }, current: Lang) =>
    current === 'en' ? item.en : item.zh

  return (
    // 对话列收窄到 3xl：问答在宽栏里换行位置难跟，窄栏更好读
    <section className="mx-auto flex min-h-panel w-full max-w-3xl flex-col">
      <PageHeader title={t('ask.title')} description={t('ask.description')}>
        <Button
          variant="secondary"
          size="sm"
          aria-expanded={showSettings}
          onClick={() => setShowSettings(open => !open)}
        >
          {t('ask.modelButton', { mode: modelLabel })}
        </Button>
      </PageHeader>

      {showSettings && <ModelSettingsPanel settings={settings} onChange={update} />}

      {/* 还没提问时把示例卡片垂直居中，否则窄栏顶部一小块、下面一大片空白 */}
      <div className={`flex flex-1 flex-col gap-6 ${history.length === 0 ? 'justify-center' : ''}`}>
        {history.length === 0 && (
          <div className="card p-8 text-center">
            <p className="font-serif text-base text-ink-500">{t('ask.suggestionsTitle')}</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map(s => (
                <Chip key={s.zh} onClick={() => submit(s.zh)}>
                  {suggestionLabel(s, lang)}
                </Chip>
              ))}
            </div>
            <p className="mt-5 text-xs leading-relaxed text-ink-400">
              {t('ask.suggestionsHint')}
            </p>
          </div>
        )}

        {history.map((ex, i) => (
          <div key={i} className="space-y-4 animate-fade-up">
            <div className="flex justify-end">
              {/* pre-wrap：用户自己按下的换行要留住；break-words：长英文不至于撑破气泡 */}
              <div className="max-w-md whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-cinnabar-500 px-4 py-2.5 text-sm leading-relaxed text-paper-50 shadow-card">
                {ex.question}
              </div>
            </div>
            <div className="card px-5 py-4">
              <Markdown content={ex.answer.answer} />
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-paper-200 pt-3 text-xs text-ink-400">
                <span>{t('ask.cited', { count: ex.answer.retrieved_count })}</span>
                <span aria-hidden="true" className="h-1 w-1 rounded-full bg-paper-400" />
                <span>
                  {ex.answer.llm_used
                    ? t('ask.aiAnswer', { model: ex.answer.model ?? '' })
                    : t('ask.localMode')}
                </span>
                {/* 记录已自动存下，这里给一个去处——不然用户根本不知道有「回响」 */}
                <Link
                  to="/history"
                  className="ml-auto rounded transition-colors hover:text-cinnabar-600"
                >
                  {t('ask.saved')}
                </Link>
              </div>
            </div>
          </div>
        ))}

        {asking && (
          <div className="flex justify-start">
            <div className="card flex items-center gap-2.5 px-5 py-3.5">
              <span
                aria-hidden="true"
                className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-paper-300 border-t-cinnabar-500"
              />
              <span className="text-sm text-ink-500">{t('ask.thinking')}</span>
            </div>
          </div>
        )}

        {error && <ErrorBox message={error} />}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={e => {
          e.preventDefault()
          void submit(question)
        }}
        className="sticky bottom-4 mt-6"
      >
        {/* 焦点环挂在整条输入栏上：输入框本身无边框，在它上面画环会很突兀。
            items-end：输入框长高后按钮贴着底边，才不会浮在中间。 */}
        <div className="card flex items-end gap-2 p-2 pl-4 shadow-composer focus-within:border-cinnabar-400 focus-within:ring-2 focus-within:ring-cinnabar-400/30">
          <textarea
            ref={composerRef}
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={handleComposerKeyDown}
            placeholder={t('ask.placeholder')}
            aria-label={t('ask.inputLabel')}
            maxLength={MAX_QUESTION_LENGTH}
            rows={1}
            className="max-h-40 min-w-0 flex-1 resize-none overflow-y-auto bg-transparent py-2 font-serif leading-relaxed text-ink-900 outline-none placeholder:text-ink-400 focus-visible:ring-0"
          />
          <Button type="submit" disabled={asking || !question.trim()}>
            {t('ask.submit')}
          </Button>
        </div>
        <p className="mt-2 text-center text-xs text-ink-400">{t('ask.composerHint')}</p>
      </form>
    </section>
  )
}

import { useRef, useState } from 'react'
import { api, type AskResponse } from '../api/client'
import Markdown from '../components/Markdown'
import { ErrorBox } from '../components/Status'
import Button from '../components/ui/Button'
import Chip from '../components/ui/Chip'
import PageHeader from '../components/ui/PageHeader'

interface Exchange {
  question: string
  answer: AskResponse
}

const SUGGESTIONS = [
  '工作中遇到小人怎么办？',
  '迷茫的时候该怎么选择方向？',
  '如何面对失败和挫折？',
  '怎样才能坚持长期目标？',
]

export default function Advisor() {
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<Exchange[]>([])
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  async function submit(q: string) {
    const trimmed = q.trim()
    if (!trimmed || asking) return
    setAsking(true)
    setError(null)
    try {
      const answer = await api.ask(trimmed)
      setHistory(prev => [...prev, { question: trimmed, answer }])
      setQuestion('')
      requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }))
    } catch (err) {
      setError(err instanceof Error ? err.message : '请求失败，请稍后再试')
    } finally {
      setAsking(false)
    }
  }

  return (
    // 对话列收窄到 3xl：问答在宽栏里换行位置难跟，窄栏更好读
    <section className="mx-auto flex min-h-panel w-full max-w-3xl flex-col">
      <PageHeader
        title="求教"
        description="向人生导师讲述你的问题或困境，它会从经典智慧中寻找答案"
      />

      {/* 还没提问时把示例卡片垂直居中，否则窄栏顶部一小块、下面一大片空白 */}
      <div className={`flex flex-1 flex-col gap-6 ${history.length === 0 ? 'justify-center' : ''}`}>
        {history.length === 0 && (
          <div className="card p-8 text-center">
            <p className="font-serif text-base text-ink-500">说说你的困惑，例如：</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map(s => (
                <Chip key={s} onClick={() => submit(s)}>
                  {s}
                </Chip>
              ))}
            </div>
          </div>
        )}

        {history.map((ex, i) => (
          <div key={i} className="space-y-4 animate-fade-up">
            <div className="flex justify-end">
              <div className="max-w-md rounded-2xl rounded-br-md bg-cinnabar-500 px-4 py-2.5 text-sm leading-relaxed text-paper-50 shadow-card">
                {ex.question}
              </div>
            </div>
            <div className="card px-5 py-4">
              <Markdown content={ex.answer.answer} />
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-paper-200 pt-3 text-xs text-ink-400">
                <span>引用 {ex.answer.retrieved_count} 段经典</span>
                <span aria-hidden="true" className="h-1 w-1 rounded-full bg-paper-400" />
                <span>
                  {ex.answer.llm_used
                    ? `AI 深度解读 · ${ex.answer.model}`
                    : '本地检索模式'}
                </span>
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
              <span className="text-sm text-ink-500">正在翻阅经典…</span>
            </div>
          </div>
        )}

        {error && <ErrorBox message={error} />}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={e => {
          e.preventDefault()
          submit(question)
        }}
        className="sticky bottom-4 mt-6"
      >
        {/* 焦点环挂在整条输入栏上：输入框本身无边框，在它上面画环会很突兀 */}
        <div className="card flex items-center gap-2 p-2 pl-4 shadow-composer focus-within:border-cinnabar-400 focus-within:ring-2 focus-within:ring-cinnabar-400/30">
          <input
            value={question}
            onChange={e => setQuestion(e.target.value)}
            placeholder="输入你的问题或困境…"
            aria-label="你的问题或困境"
            maxLength={500}
            className="min-w-0 flex-1 bg-transparent py-2 font-serif text-ink-900 outline-none placeholder:text-ink-400 focus-visible:ring-0"
          />
          <Button type="submit" disabled={asking || !question.trim()}>
            求教
          </Button>
        </div>
      </form>
    </section>
  )
}

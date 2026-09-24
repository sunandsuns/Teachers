import { useState } from 'react'
import { ErrorBox } from '../../components/Status'
import { Button, Collapse, PageHeader } from '../../components/ui'
import { useI18n } from '../../i18n'
import Composer from './Composer'
import ExchangeCard from './ExchangeCard'
import ModelSettingsPanel from './ModelSettingsPanel'
import { StreamingAnswer, ThinkingBubble } from './Pending'
import SuggestionChips from './SuggestionChips'
import { useAdvisor } from './useAdvisor'

/**
 * 求教。
 *
 * 这个文件里**没有一行网络请求**——全部在 `useAdvisor` 里。
 * 它只回答一个问题："现在该显示什么"，共四种状态：
 *
 *   没有对话  → 示例卡（垂直居中）
 *   有对话    → 一问一答依次排开
 *   在飞      → 云端流式正文 / 内置模型的转圈
 *   出错      → 错误条（**不遮挡**已有对话，答案还在上面）
 *
 * 这种"页面只做编排"的写法，好处是改版式时不可能碰坏请求逻辑，
 * 反之亦然。两个方向各自独立可测。
 */
export default function AdvisorPage() {
  const { t } = useI18n()
  const [showSettings, setShowSettings] = useState(false)
  const advisor = useAdvisor()

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
          {t('ask.modelButton', { mode: advisor.modelLabel })}
        </Button>
      </PageHeader>

      {showSettings && (
        <Collapse>
          <ModelSettingsPanel settings={advisor.settings} onChange={advisor.update} />
        </Collapse>
      )}

      {/* 还没提问时把示例卡片垂直居中，否则窄栏顶部一小块、下面一大片空白 */}
      <div
        className={`flex flex-1 flex-col gap-6 ${
          advisor.history.length === 0 ? 'justify-center' : ''
        }`}
      >
        {advisor.history.length === 0 && <SuggestionChips onPick={advisor.submit} />}

        {advisor.history.map((exchange, i) => (
          <ExchangeCard key={i} exchange={exchange} />
        ))}

        {/* 云端是流式的：有正文就边出边渲染，还没出第一个字时才转圈 */}
        {advisor.streaming !== null ? (
          <StreamingAnswer text={advisor.streaming} />
        ) : (
          advisor.asking && <ThinkingBubble />
        )}

        {advisor.error && <ErrorBox message={advisor.error} />}
        <div ref={advisor.bottomRef} />
      </div>

      <Composer
        value={advisor.question}
        onChange={advisor.setQuestion}
        onSubmit={() => advisor.submit(advisor.question)}
        busy={advisor.asking}
      />
    </section>
  )
}

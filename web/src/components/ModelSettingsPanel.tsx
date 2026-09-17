import { useState } from 'react'
import { api } from '../api/client'
import type { ModelSettings } from '../hooks/useModelSettings'
import { isComplete, toPayload } from '../hooks/useModelSettings'
import Button from './ui/Button'
import Segmented from './ui/Segmented'

/**
 * 求教页的模型来源选择：用内置的默认模型，或填自己的接口地址与 Key。
 *
 * 做成可折叠面板而不是独立设置页：它只影响"求教"这一件事，
 * 挪到别处反而要用户多跑一趟。
 */

type Probe =
  | { state: 'idle' }
  | { state: 'testing' }
  | { state: 'ok'; message: string; models: string[] }
  | { state: 'fail'; message: string; models: string[] }

const MODE_OPTIONS = [
  { value: 'default' as const, label: '默认模型' },
  { value: 'custom' as const, label: '自定义模型' },
]

export default function ModelSettingsPanel({
  settings,
  onChange,
}: {
  settings: ModelSettings
  onChange: (patch: Partial<ModelSettings>) => void
}) {
  const [probe, setProbe] = useState<Probe>({ state: 'idle' })

  /** 改了任何字段，上一次的测试结论就不再可信，清掉免得误读。 */
  function change(patch: Partial<ModelSettings>) {
    setProbe({ state: 'idle' })
    onChange(patch)
  }

  async function test() {
    const payload = toPayload({ ...settings, mode: 'custom' })
    if (!payload) {
      setProbe({ state: 'fail', message: '请先填写接口地址与 API Key', models: [] })
      return
    }
    setProbe({ state: 'testing' })
    try {
      const result = await api.probeModel(payload)
      if (result.ok) {
        setProbe({
          state: 'ok',
          message: `连接成功，当前使用 ${result.model}`,
          models: result.models,
        })
      } else {
        setProbe({
          state: 'fail',
          message: result.error || '连不上这个地址',
          models: result.models,
        })
      }
    } catch (err) {
      setProbe({
        state: 'fail',
        message: err instanceof Error ? err.message : '请求失败，请稍后再试',
        models: [],
      })
    }
  }

  return (
    <div className="card mb-6 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented
          value={settings.mode}
          options={MODE_OPTIONS}
          onChange={mode => change({ mode })}
        />
        {settings.mode === 'custom' && (
          <Button
            variant="secondary"
            size="sm"
            onClick={test}
            disabled={probe.state === 'testing' || !isComplete(settings)}
          >
            {probe.state === 'testing' ? '正在连接…' : '测试连接'}
          </Button>
        )}
      </div>

      {settings.mode === 'default' ? (
        <p className="mt-3 text-sm leading-relaxed text-ink-500">
          使用应用自带的模型配置，开箱即用。若想接自己的模型
          （例如公司的私有部署、或另一个服务商的 Key），切到「自定义模型」。
        </p>
      ) : (
        <div className="mt-4 space-y-4">
          <Field
            id="llm-base-url"
            label="接口地址"
            value={settings.base_url}
            placeholder="https://api.example.com/v1"
            hint="OpenAI 兼容接口的根地址，末尾的 /v1 要带上。"
            onChange={value => change({ base_url: value })}
          />
          <Field
            id="llm-api-key"
            label="API Key"
            value={settings.api_key}
            placeholder="sk-…"
            type="password"
            hint="只保存在这台电脑的浏览器里，不会上传到别处，也不会写进程序文件。"
            onChange={value => change({ api_key: value })}
          />
          <Field
            id="llm-model"
            label="模型名（可留空）"
            value={settings.model}
            placeholder="留空则自动挑选"
            hint="不确定填什么就留空，程序会从该地址可用的模型里挑一个能出字的。"
            onChange={value => change({ model: value })}
          />

          <div className="text-sm" aria-live="polite">
            {probe.state === 'testing' && <span className="text-ink-500">正在连接…</span>}
            {probe.state === 'ok' && (
              <span className="text-celadon-700">
                {probe.message}
                {probe.models.length > 0 && `（该地址提供 ${probe.models.length} 个模型）`}
              </span>
            )}
            {probe.state === 'fail' && (
              <span className="text-cinnabar-600">
                {probe.message}
                {probe.models.length > 0 && `（该地址提供了 ${probe.models.length} 个模型，但没一个能出字）`}
              </span>
            )}
          </div>

          {!isComplete(settings) && (
            <p className="text-xs text-ink-400">
              接口地址与 API Key 都填上之后，「求教」才会走这个模型；在此之前仍用默认模型。
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function Field({
  id,
  label,
  value,
  placeholder,
  hint,
  onChange,
  type = 'text',
}: {
  id: string
  label: string
  value: string
  placeholder: string
  hint?: string
  type?: 'text' | 'password'
  onChange: (value: string) => void
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink-700">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        autoComplete="off"
        spellCheck={false}
        className="field font-mono text-sm"
      />
      {hint && <p className="mt-1.5 text-xs leading-relaxed text-ink-400">{hint}</p>}
    </div>
  )
}

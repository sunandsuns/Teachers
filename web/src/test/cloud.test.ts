/** WorkBuddy 云模型的选取与错误归类。
 *
 * 这两件事都是**纯逻辑**，而且是"看着能用、坏了才发现"的那一类：
 *
 * - 选错模型。云端目录有 30 个模型，第一条是 `auto`（自动匹配），输出深浅不定。
 *   偏好列表落空时能不能退回目录默认，决定了它是"始终能用"还是"偶尔调不通"。
 * - 错误归类。界面靠它说清"为什么降级了"，归错档会给出牛头不对马嘴的解释。
 *
 * SDK 在这里被整个替换掉——用例要验的是自己的判断，不是 SDK 会不会发请求。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cloudErrorInfo, listCloudModels, pickCloudModel, type CloudModel } from '../lib/cloud'

// vi.mock 会被提到文件最前面执行，所以工厂里用到的桩必须一起提上去
// （vi.hoisted），否则就是"在初始化前访问 modelsList"。
const { modelsList } = vi.hoisted(() => ({ modelsList: vi.fn() }))

vi.mock('@tencent-ai/workbuddy-cloud-sdk', () => ({
  createWorkBuddyCloud: () => ({ llm: { models: { list: modelsList } } }),
}))

beforeEach(() => {
  modelsList.mockReset()
})

function model(id: string, extra: Partial<CloudModel> = {}): CloudModel {
  return { id, name: id, ...extra }
}

describe('云端模型目录', () => {
  it('丢掉已下线的模型，并给没配名字的补上 id', async () => {
    modelsList.mockResolvedValue([
      { id: 'auto', name: '自动' },
      { id: 'deepseek-v4-pro', name: '' },
      { id: 'retired', name: '退役', enabled: false },
      { id: 'disabled-flag', name: '停用', disabled: true },
    ])

    const models = await listCloudModels()

    expect(models.map(m => m.id)).toEqual(['auto', 'deepseek-v4-pro'])
    // 名字为空时退回 id：界面上宁可显示一个生硬的 id，
    // 也不能显示一个空白的按钮
    expect(models[1].name).toBe('deepseek-v4-pro')
  })
})

describe('挑模型', () => {
  it('偏好列表里第一个出现的就是它', () => {
    const picked = pickCloudModel([
      model('auto', { isDefault: true }),
      model('glm-5.3'),
      model('deepseek-v4-pro'),
    ])
    expect(picked?.id).toBe('deepseek-v4-pro')
  })

  it('偏好一个都没中时，退回目录标的那一个', () => {
    const picked = pickCloudModel([
      model('auto', { isDefault: true }),
      model('qwen-something'),
    ])
    expect(picked?.id).toBe('auto')
  })

  it('连默认都没标时取第一条——偏好落空不该变成调不通', () => {
    const picked = pickCloudModel([model('first'), model('second')])
    expect(picked?.id).toBe('first')
  })

  it('目录是空的时候返回 null，交给调用方降级', () => {
    expect(pickCloudModel([])).toBeNull()
  })
})

describe('错误归类', () => {
  function coded(code: string): Error {
    return Object.assign(new Error('上游返回：' + code), { error: { code } })
  }

  it.each([
    ['auth_invalid_credential', 'auth'],
    ['quota_exceeded', 'quota'],
    ['gateway_timeout', 'unavailable'],
    ['model_not_found', 'unavailable'],
    ['request_invalid_body', 'bad_request'],
    ['internal_error', 'internal'],
  ])('%s → %s', (code, kind) => {
    expect(cloudErrorInfo(coded(code)).kind).toBe(kind)
  })

  it('认不出代码时归到 unknown，并保留原文供排查', () => {
    const info = cloudErrorInfo(coded('something_new'))
    expect(info.kind).toBe('unknown')
    expect(info.detail).toContain('something_new')
  })

  it('连错误对象都不是（比如被 throw 的字符串）也能给出 human 可读的 detail', () => {
    const info = cloudErrorInfo('纯字符串错误')
    expect(info.kind).toBe('unknown')
    expect(info.detail).toBe('纯字符串错误')
  })
})

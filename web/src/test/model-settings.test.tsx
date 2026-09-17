/** 求教页的模型来源：默认模型 / 自定义端点。
 *
 * 这里覆盖的核心契约是**"请求里到底带了什么"**——界面上的切换看着生效，
 * 但若没真的把配置随请求发出去，用户的 Key 就白填了。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: {
    listBooks: vi.fn(),
    getBook: vi.fn(),
    listChapters: vi.fn(),
    getChapter: vi.fn(),
    getSource: vi.fn(),
    search: vi.fn(),
    ask: vi.fn(),
    probeModel: vi.fn(),
    askStatus: vi.fn(),
    dailyInsight: vi.fn(),
    randomInsight: vi.fn(),
    insightThemes: vi.fn(),
    insightsByTheme: vi.fn(),
    insightsByBook: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

const ANSWER = {
  question: '如何面对挫折',
  answer: '天行健，君子以自强不息。',
  retrieved_count: 3,
  llm_used: true,
  model: 'some-model',
}

function renderAskPage() {
  window.history.replaceState({}, '', '/ask')
  return render(
    <MemoryRouter initialEntries={['/ask']}>
      <App />
    </MemoryRouter>,
  )
}

/** 展开求教页顶部的模型设置面板。 */
async function openPanel(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: /模型：/ }))
}

async function fillCustomEndpoint(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: '自定义模型' }))
  await user.type(screen.getByLabelText('接口地址'), 'https://my.example.com/v1')
  await user.type(screen.getByLabelText('API Key'), 'sk-mine')
}

async function askAQuestion(user: ReturnType<typeof userEvent.setup>, text = '如何面对挫折') {
  await user.type(screen.getByPlaceholderText('输入你的问题或困境…'), text)
  await user.click(screen.getByRole('button', { name: '求教' }))
  await waitFor(() => expect(mockedApi.ask).toHaveBeenCalled())
}

describe('求教的模型来源', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.ask.mockResolvedValue(ANSWER)
  })

  it('默认模型：请求里不带自定义端点', async () => {
    const user = userEvent.setup()
    renderAskPage()
    await askAQuestion(user)

    expect(mockedApi.ask.mock.calls[0][2]).toBeNull()
  })

  it('自定义模型填全后，请求带上地址与 Key', async () => {
    const user = userEvent.setup()
    renderAskPage()

    await openPanel(user)
    await fillCustomEndpoint(user)
    await askAQuestion(user)

    expect(mockedApi.ask.mock.calls[0][2]).toEqual({
      base_url: 'https://my.example.com/v1',
      api_key: 'sk-mine',
      model: '',
    })
  })

  it('自定义模型只填了一半时不生效，仍用默认模型', async () => {
    const user = userEvent.setup()
    renderAskPage()

    await openPanel(user)
    await user.click(screen.getByRole('button', { name: '自定义模型' }))
    // 只填地址，不填 Key
    await user.type(screen.getByLabelText('接口地址'), 'https://my.example.com/v1')
    await askAQuestion(user)

    expect(mockedApi.ask.mock.calls[0][2]).toBeNull()
  })

  it('填全后顶部按钮如实显示当前用的是自定义模型', async () => {
    const user = userEvent.setup()
    renderAskPage()

    await openPanel(user)
    await fillCustomEndpoint(user)

    expect(screen.getByRole('button', { name: /模型：自定义/ })).toBeTruthy()
  })

  it('选了自定义却没填全时，按钮显示「未填写」而不是「默认」', async () => {
    // 显示"默认"虽然事实正确，但和用户刚点的那一下对不上，会让人以为白点了
    const user = userEvent.setup()
    renderAskPage()

    await openPanel(user)
    await user.click(screen.getByRole('button', { name: '自定义模型' }))

    expect(screen.getByRole('button', { name: /模型：未填写/ })).toBeTruthy()
  })

  it('测试连接成功时展示后端选中的模型', async () => {
    mockedApi.probeModel.mockResolvedValue({
      ok: true,
      base_url: 'https://my.example.com/v1',
      model: 'my-model',
      models: ['my-model', 'other-model'],
      error: '',
    })
    const user = userEvent.setup()
    renderAskPage()

    await openPanel(user)
    await fillCustomEndpoint(user)
    await user.click(screen.getByRole('button', { name: '测试连接' }))

    await waitFor(() => expect(screen.getByText(/连接成功/)).toBeTruthy())
    expect(screen.getByText(/my-model/)).toBeTruthy()
  })

  it('测试连接失败时展示后端给出的原因', async () => {
    mockedApi.probeModel.mockResolvedValue({
      ok: false,
      base_url: 'https://my.example.com/v1',
      model: '',
      models: [],
      error: 'HTTP 401：密钥无效',
    })
    const user = userEvent.setup()
    renderAskPage()

    await openPanel(user)
    await fillCustomEndpoint(user)
    await user.click(screen.getByRole('button', { name: '测试连接' }))

    await waitFor(() => expect(screen.getByText(/HTTP 401/)).toBeTruthy())
  })

  it('设置写进 localStorage，刷新后仍然生效', async () => {
    const user = userEvent.setup()
    const first = renderAskPage()

    await openPanel(user)
    await fillCustomEndpoint(user)
    first.unmount()

    renderAskPage()
    await askAQuestion(user)

    expect(mockedApi.ask.mock.calls[0][2]).toEqual({
      base_url: 'https://my.example.com/v1',
      api_key: 'sk-mine',
      model: '',
    })
  })
})

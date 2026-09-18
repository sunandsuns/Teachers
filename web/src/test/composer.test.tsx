import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Advisor from '../pages/Advisor'
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
    listHistory: vi.fn(),
    historyStatus: vi.fn(),
    deleteHistory: vi.fn(),
    clearHistory: vi.fn(),
    dailyInsight: vi.fn(),
    randomInsight: vi.fn(),
    insightThemes: vi.fn(),
    insightsByTheme: vi.fn(),
    insightsByBook: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

/** 输入区：一个字打不完的问题，得能换行、能直接发出去。
 *
 * 这一组用例锁住三条容易写错的行为：回车发送、Shift+回车换行、
 * 以及**中文输入法组词时的回车不能当成发送**（否则半截拼音会被发出去）。
 */
describe('求教输入框', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.ask.mockResolvedValue({
      question: '占位',
      answer: '天行健，君子以自强不息。',
      retrieved_count: 3,
      llm_used: false,
      model: null,
      history_id: 1,
    })
  })

  function setup() {
    return render(
      <MemoryRouter initialEntries={['/ask']}>
        <Advisor />
      </MemoryRouter>,
    )
  }

  it('回车直接发送，问题立刻发出去', async () => {
    setup()
    const user = userEvent.setup()
    const box = await screen.findByPlaceholderText('输入你的问题或困境…')

    await user.type(box, '我该如何面对失败？')
    await user.keyboard('{Enter}')

    await waitFor(() => expect(mockedApi.ask).toHaveBeenCalledTimes(1))
    expect(mockedApi.ask.mock.calls[0][0]).toBe('我该如何面对失败？')
  })

  it('发送后输入框清空，不复用上一条', async () => {
    setup()
    const user = userEvent.setup()
    const box = (await screen.findByPlaceholderText(
      '输入你的问题或困境…',
    )) as HTMLTextAreaElement

    await user.type(box, '第一个问题')
    await user.keyboard('{Enter}')

    await waitFor(() => expect(box.value).toBe(''))
  })

  it('Shift + 回车是换行，不发送', async () => {
    setup()
    const user = userEvent.setup()
    const box = (await screen.findByPlaceholderText(
      '输入你的问题或困境…',
    )) as HTMLTextAreaElement

    await user.type(box, '第一行')
    await user.keyboard('{Shift>}{Enter}{/Shift}')

    expect(mockedApi.ask).not.toHaveBeenCalled()
    // 换行进了输入框（具体是 \n 还是别的空白由浏览器决定，只要求内容没丢）
    expect(box.value).toContain('第一行')
  })

  it('多行问题原样发出去，换行不被压掉', async () => {
    setup()
    const box = await screen.findByPlaceholderText('输入你的问题或困境…')

    // 用 change 直接造出多行内容：userEvent 逐字敲的组合键在 jsdom 里
    // 不一定真会插入换行，那样测的就是 userEvent 而不是我们的代码
    fireEvent.change(box, { target: { value: '第一行\n第二行' } })
    fireEvent.click(screen.getByRole('button', { name: '求教' }))

    await waitFor(() => expect(mockedApi.ask).toHaveBeenCalledTimes(1))
    expect(mockedApi.ask.mock.calls[0][0]).toBe('第一行\n第二行')
  })

  it('输入法组词时的回车只选词，不发送', async () => {
    setup()
    const box = await screen.findByPlaceholderText('输入你的问题或困境…')

    fireEvent.change(box, { target: { value: '我正在打字' } })
    // 组词中：keydown 带 isComposing
    fireEvent.keyDown(box, { key: 'Enter', isComposing: true })

    expect(mockedApi.ask).not.toHaveBeenCalled()
  })

  it('输入框是多行控件，且给得出换行提示', async () => {
    setup()
    const box = await screen.findByPlaceholderText('输入你的问题或困境…')

    expect(box.tagName).toBe('TEXTAREA')
    expect(screen.getByText(/Shift \+ Enter/)).toBeTruthy()
  })
})

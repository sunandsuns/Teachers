/** 「回响」（求教历史）页面。
 *
 * 这一页的契约有三条，别的都是排版：
 *
 * 1. **按话题聚合**——同一件事的追问落在一张卡片里，点开才展开那段对话。
 *    收起时给一段预览，不点开也能想起聊到哪了。
 * 2. **列表与概况是两件事**——概况来自 `/api/history/status`，它同时负责告诉
 *    用户"记录留多久、下次什么时候清理"。删掉东西之后那句"共 N 条"必须跟着变，
 *    否则界面当场自相矛盾。
 * 3. **数据库不可用不是错误页**——`available: false` 时要照常渲染、说明原因，
 *    而不是弹一个红色报错或者显示成"还没有记录"（那会让人以为记录丢了）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import History from '../pages/History'
import type { HistoryItem, HistoryStatus, TopicItem } from '../api/client'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: {
    listTopics: vi.fn(),
    topicRecords: vi.fn(),
    historyStatus: vi.fn(),
    deleteHistory: vi.fn(),
    deleteTopic: vi.fn(),
    clearHistory: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

const NOW = Date.now() / 1000

const TOPICS: TopicItem[] = [
  {
    id: 't1',
    title: '工作中遇到小人怎么办？',
    question_count: 2,
    first_ts: NOW - 4000,
    last_ts: NOW,
    latest_question: '那要是躲不开呢？',
    latest_answer: '君子坦荡荡，小人长戚戚。',
  },
  {
    id: 'solo:9',
    title: '迷茫的时候该怎么选择方向？',
    question_count: 1,
    first_ts: NOW - 8000,
    last_ts: NOW - 8000,
    latest_question: '迷茫的时候该怎么选择方向？',
    latest_answer: '知止而后有定。',
  },
]

const ASK_RECORDS: HistoryItem[] = [
  {
    id: 2,
    question: '工作中遇到小人怎么办？',
    answer: '君子坦荡荡，小人长戚戚。',
    model: null,
    llm_used: false,
    retrieved_count: 5,
    conversation_id: 't1',
    created_at: new Date((NOW - 4000) * 1000).toISOString(),
    created_ts: NOW - 4000,
  },
  {
    id: 1,
    question: '那要是躲不开呢？',
    answer: '敬而远之，不与之争。',
    model: 'some-model',
    llm_used: true,
    retrieved_count: 3,
    conversation_id: 't1',
    created_at: new Date(NOW * 1000).toISOString(),
    created_ts: NOW,
  },
]

/** 只有一个话题一张卡片时用的那条记录（老记录的 solo 话题）。 */
const SOLO_RECORD: HistoryItem = {
  id: 9,
  question: '迷茫的时候该怎么选择方向？',
  answer: '知止而后有定。',
  model: null,
  llm_used: false,
  retrieved_count: 1,
  conversation_id: null,
  created_at: new Date((NOW - 8000) * 1000).toISOString(),
  created_ts: NOW - 8000,
}

const STATUS: HistoryStatus = {
  available: true,
  error: '',
  db_path: 'C:/人生导师/data/history.db',
  total: 2,
  retention_days: 15,
  last_purge_at: '2026-09-17T13:00:00+08:00',
  // 用本地时间构造再转 ISO：直接写死时区偏移的话，换个时区的机器上会差一天
  next_purge_at: new Date(2026, 9, 2, 13, 0, 0).toISOString(),
  size_bytes: 4096,
}

/** 求教页的替身：把带过来的查询串显示出来，"再问一次"有没有带话题一目了然。 */
function AskStub() {
  const location = useLocation()
  return <p>求教页面{location.search}</p>
}

function renderHistory() {
  return render(
    <MemoryRouter initialEntries={['/history']}>
      <Routes>
        <Route path="/history" element={<History />} />
        <Route path="/ask" element={<AskStub />} />
      </Routes>
    </MemoryRouter>,
  )
}

/** 打开第一个话题卡片。 */
async function openFirstTopic(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: /工作中遇到小人怎么办/ }))
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.listTopics.mockResolvedValue({ available: true, error: '', total: 2, items: TOPICS })
  mockedApi.topicRecords.mockResolvedValue({
    available: true,
    error: '',
    total: 2,
    items: ASK_RECORDS,
  })
  mockedApi.historyStatus.mockResolvedValue(STATUS)
  mockedApi.deleteHistory.mockResolvedValue({ deleted: 1 })
  mockedApi.deleteTopic.mockResolvedValue({ deleted: 2 })
  mockedApi.clearHistory.mockResolvedValue({ deleted: 2 })
})

describe('话题列表', () => {
  it('把每个话题列成一张卡片，标出问了几轮', async () => {
    renderHistory()

    await waitFor(() => expect(screen.getByText('工作中遇到小人怎么办？')).toBeTruthy())
    expect(screen.getByText('迷茫的时候该怎么选择方向？')).toBeTruthy()
    expect(screen.getByText('2 轮追问')).toBeTruthy()
    expect(screen.getByText('1 轮追问')).toBeTruthy()
  })

  it('收起时给一段预览，不点开也能想起聊到哪', async () => {
    renderHistory()

    await waitFor(() => expect(screen.getByText(/君子坦荡荡/)).toBeTruthy())
  })

  it('没点开就不去取记录，省一次请求', async () => {
    renderHistory()

    await waitFor(() => expect(screen.getByText('工作中遇到小人怎么办？')).toBeTruthy())
    expect(mockedApi.topicRecords).not.toHaveBeenCalled()
  })

  it('展开后显示这段对话的问答与出处信息', async () => {
    const user = userEvent.setup()
    renderHistory()
    await openFirstTopic(user)

    await waitFor(() => expect(mockedApi.topicRecords).toHaveBeenCalledWith('t1'))
    await waitFor(() => expect(screen.getByText('引用 5 段经典')).toBeTruthy())
    // 两种作答模式如实区分
    expect(screen.getByText('本地检索模式')).toBeTruthy()
    expect(screen.getByText('AI 深度解读 · some-model')).toBeTruthy()
  })

  it('再点一次就收起', async () => {
    const user = userEvent.setup()
    renderHistory()
    await openFirstTopic(user)
    await waitFor(() => expect(screen.getByText('引用 5 段经典')).toBeTruthy())

    await user.click(screen.getByRole('button', { name: /工作中遇到小人怎么办/ }))

    await waitFor(() => expect(screen.queryByText('引用 5 段经典')).toBeNull())
  })

  it('说明保留期限与下次清理时间', async () => {
    renderHistory()

    await waitFor(() => expect(screen.getByText(/只保留最近 15 天/)).toBeTruthy())
    expect(screen.getByText(/下次自动清理 10 月 2 日/)).toBeTruthy()
    expect(screen.getByText(/history\.db/)).toBeTruthy()
  })

  it('空的时候给出引导而不是一片空白', async () => {
    mockedApi.listTopics.mockResolvedValue({ available: true, error: '', total: 0, items: [] })
    mockedApi.historyStatus.mockResolvedValue({ ...STATUS, total: 0 })

    renderHistory()

    await waitFor(() => expect(screen.getByText(/还没有求教记录/)).toBeTruthy())
  })

  it('话题多于本页时提供继续加载', async () => {
    mockedApi.listTopics.mockResolvedValue({ available: true, error: '', total: 25, items: TOPICS })
    mockedApi.historyStatus.mockResolvedValue({ ...STATUS, total: 25 })
    const user = userEvent.setup()
    renderHistory()

    const more = await screen.findByRole('button', { name: /加载更多/ })
    expect(more.textContent).toContain('还有 23 个话题')

    mockedApi.listTopics.mockResolvedValue({ available: true, error: '', total: 25, items: [] })
    await user.click(more)

    await waitFor(() => expect(mockedApi.listTopics).toHaveBeenLastCalledWith(20, 2))
  })
})

describe('回响的删除', () => {
  it('删掉一条后轮数与概况同时更新', async () => {
    const user = userEvent.setup()
    renderHistory()
    await openFirstTopic(user)
    await waitFor(() => expect(screen.getByText('引用 5 段经典')).toBeTruthy())

    await user.click(screen.getAllByRole('button', { name: '删除' })[0])

    await waitFor(() => expect(mockedApi.deleteHistory).toHaveBeenCalledWith(2))
    await waitFor(() => expect(screen.queryByText('君子坦荡荡，小人长戚戚。')).toBeNull())
    // 卡片上的轮数与概况那行都得跟着减，否则界面上会自相矛盾。
    // 另一个话题本来就是 1 轮，所以这会儿有两张卡片都写着"1 轮追问"
    expect(screen.getAllByText('1 轮追问')).toHaveLength(2)
    expect(screen.getByText(/共 1 条/)).toBeTruthy()
  })

  it('删掉最后一条时整张卡片撤掉', async () => {
    mockedApi.topicRecords.mockResolvedValue({
      available: true,
      error: '',
      total: 1,
      items: [SOLO_RECORD],
    })
    const user = userEvent.setup()
    renderHistory()
    await user.click(await screen.findByRole('button', { name: /迷茫的时候该怎么选择方向/ }))
    await waitFor(() => expect(screen.getByText('引用 1 段经典')).toBeTruthy())

    await user.click(screen.getAllByRole('button', { name: '删除' })[0])

    await waitFor(() => expect(screen.queryByText('迷茫的时候该怎么选择方向？')).toBeNull())
  })

  it('删除整段要先确认，取消则不动', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    renderHistory()
    await openFirstTopic(user)

    await user.click(await screen.findByRole('button', { name: '删除整段' }))

    expect(confirm).toHaveBeenCalled()
    expect(mockedApi.deleteTopic).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('确认后删掉整段，卡片消失', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderHistory()
    await openFirstTopic(user)

    await user.click(await screen.findByRole('button', { name: '删除整段' }))

    await waitFor(() => expect(mockedApi.deleteTopic).toHaveBeenCalledWith('t1'))
    await waitFor(() => expect(screen.queryByText('工作中遇到小人怎么办？')).toBeNull())
    confirm.mockRestore()
  })

  it('清空要先确认，取消则不动', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    renderHistory()

    await user.click(await screen.findByRole('button', { name: '清空' }))

    expect(confirm).toHaveBeenCalled()
    expect(mockedApi.clearHistory).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('确认后清空并重新读取', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderHistory()

    await user.click(await screen.findByRole('button', { name: '清空' }))

    await waitFor(() => expect(mockedApi.clearHistory).toHaveBeenCalled())
    // 清空之后要重新拉一次：本地把数组清掉不如以服务端为准
    await waitFor(() => expect(mockedApi.listTopics).toHaveBeenCalledTimes(2))
    confirm.mockRestore()
  })

  it('没有记录时不显示清空按钮', async () => {
    mockedApi.listTopics.mockResolvedValue({ available: true, error: '', total: 0, items: [] })
    mockedApi.historyStatus.mockResolvedValue({ ...STATUS, total: 0 })

    renderHistory()

    await waitFor(() => expect(screen.getByText(/还没有求教记录/)).toBeTruthy())
    expect(screen.queryByRole('button', { name: '清空' })).toBeNull()
  })
})

describe('回响的「再问一次」', () => {
  it('跳到求教页，并带上原问题与所属话题', async () => {
    const user = userEvent.setup()
    renderHistory()
    await openFirstTopic(user)

    await user.click((await screen.findAllByRole('button', { name: '再问一次' }))[0])

    await waitFor(() => expect(screen.getByText(/求教页面/)).toBeTruthy())
    // 带上话题，接着问的问题才归得回这件事
    expect(screen.getByText(/topic=t1/)).toBeTruthy()
  })
})

describe('数据库不可用', () => {
  const BROKEN: HistoryStatus = {
    ...STATUS,
    available: false,
    error: 'OperationalError: attempt to write a readonly database',
    total: 0,
  }

  beforeEach(() => {
    mockedApi.listTopics.mockResolvedValue({
      available: false,
      error: BROKEN.error,
      total: 0,
      items: [],
    })
    mockedApi.historyStatus.mockResolvedValue(BROKEN)
  })

  it('说明原因，而不是谎称"还没有记录"', async () => {
    renderHistory()

    await waitFor(() => expect(screen.getByText(/readonly database/)).toBeTruthy())
    expect(screen.queryByText(/还没有求教记录/)).toBeNull()
    // 还要讲清楚影响范围，免得用户以为整个应用坏了
    expect(screen.getByText(/其它功能不受影响/)).toBeTruthy()
  })
})

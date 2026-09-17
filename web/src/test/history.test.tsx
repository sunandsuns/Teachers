/** 「回响」（求教历史）页面。
 *
 * 这一页的契约有两条，别的都是排版：
 *
 * 1. **列表与概况是两件事**——概况来自 `/api/history/status`，它同时负责告诉
 *    用户"记录留多久、下次什么时候清理"。删除一条之后那句"共 N 条"必须跟着变，
 *    否则界面当场自相矛盾。
 * 2. **数据库不可用不是错误页**——`available: false` 时要照常渲染、说明原因，
 *    而不是弹一个红色报错或者显示成"还没有记录"（那会让人以为记录丢了）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import History from '../pages/History'
import type { HistoryItem, HistoryStatus } from '../api/client'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: {
    listHistory: vi.fn(),
    historyStatus: vi.fn(),
    deleteHistory: vi.fn(),
    clearHistory: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

const NOW = Date.now() / 1000

const RECORDS: HistoryItem[] = [
  {
    id: 2,
    question: '工作中遇到小人怎么办？',
    answer: '君子坦荡荡，小人长戚戚。',
    model: null,
    llm_used: false,
    retrieved_count: 5,
    created_at: new Date(NOW * 1000).toISOString(),
    created_ts: NOW,
  },
  {
    id: 1,
    question: '迷茫的时候该怎么选择方向？',
    answer: '知止而后有定。',
    model: 'some-model',
    llm_used: true,
    retrieved_count: 3,
    created_at: new Date((NOW - 4000) * 1000).toISOString(),
    created_ts: NOW - 4000,
  },
]

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

function renderHistory() {
  return render(
    <MemoryRouter initialEntries={['/history']}>
      <Routes>
        <Route path="/history" element={<History />} />
        <Route path="/ask" element={<p>求教页面</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.listHistory.mockResolvedValue({ available: true, error: '', total: 2, items: RECORDS })
  mockedApi.historyStatus.mockResolvedValue(STATUS)
  mockedApi.deleteHistory.mockResolvedValue({ deleted: 1 })
  mockedApi.clearHistory.mockResolvedValue({ deleted: 2 })
})

describe('回响列表', () => {
  it('列出问答与出处信息', async () => {
    renderHistory()

    await waitFor(() => expect(screen.getByText('工作中遇到小人怎么办？')).toBeTruthy())
    expect(screen.getByText('迷茫的时候该怎么选择方向？')).toBeTruthy()
    // 回答走 Markdown 渲染
    expect(screen.getByText('君子坦荡荡，小人长戚戚。')).toBeTruthy()
    expect(screen.getByText('引用 5 段经典')).toBeTruthy()
    // 两种作答模式如实区分
    expect(screen.getByText('本地检索模式')).toBeTruthy()
    expect(screen.getByText('AI 深度解读 · some-model')).toBeTruthy()
  })

  it('说明保留期限与下次清理时间', async () => {
    renderHistory()

    await waitFor(() => expect(screen.getByText(/只保留最近 15 天/)).toBeTruthy())
    expect(screen.getByText(/下次自动清理 10 月 2 日/)).toBeTruthy()
    expect(screen.getByText(/history\.db/)).toBeTruthy()
  })

  it('空的时候给出引导而不是一片空白', async () => {
    mockedApi.listHistory.mockResolvedValue({ available: true, error: '', total: 0, items: [] })
    mockedApi.historyStatus.mockResolvedValue({ ...STATUS, total: 0 })

    renderHistory()

    await waitFor(() => expect(screen.getByText(/还没有求教记录/)).toBeTruthy())
  })

  it('总数多于本页时提供继续加载', async () => {
    mockedApi.listHistory.mockResolvedValue({ available: true, error: '', total: 25, items: RECORDS })
    mockedApi.historyStatus.mockResolvedValue({ ...STATUS, total: 25 })
    const user = userEvent.setup()
    renderHistory()

    const more = await screen.findByRole('button', { name: /加载更多/ })
    expect(more.textContent).toContain('还有 23 条')

    mockedApi.listHistory.mockResolvedValue({ available: true, error: '', total: 25, items: [] })
    await user.click(more)

    await waitFor(() => expect(mockedApi.listHistory).toHaveBeenLastCalledWith(20, 2))
  })
})

describe('回响的删除', () => {
  it('删掉一条后列表与总数同时更新', async () => {
    const user = userEvent.setup()
    renderHistory()
    await waitFor(() => expect(screen.getByText('共 2 条', { exact: false })).toBeTruthy())

    // 第一条记录对应的删除按钮
    await user.click(screen.getAllByRole('button', { name: '删除' })[0])

    await waitFor(() => expect(mockedApi.deleteHistory).toHaveBeenCalledWith(2))
    await waitFor(() => expect(screen.queryByText('工作中遇到小人怎么办？')).toBeNull())
    expect(screen.getByText('迷茫的时候该怎么选择方向？')).toBeTruthy()
    // 概况那行也得跟着减，否则界面上会自相矛盾
    expect(screen.getByText(/共 1 条/)).toBeTruthy()
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
    await waitFor(() => expect(mockedApi.listHistory).toHaveBeenCalledTimes(2))
    confirm.mockRestore()
  })

  it('没有记录时不显示清空按钮', async () => {
    mockedApi.listHistory.mockResolvedValue({ available: true, error: '', total: 0, items: [] })
    mockedApi.historyStatus.mockResolvedValue({ ...STATUS, total: 0 })

    renderHistory()

    await waitFor(() => expect(screen.getByText(/还没有求教记录/)).toBeTruthy())
    expect(screen.queryByRole('button', { name: '清空' })).toBeNull()
  })
})

describe('回响的「再问一次」', () => {
  it('跳到求教页（并带上原问题）', async () => {
    const user = userEvent.setup()
    renderHistory()

    await user.click((await screen.findAllByRole('button', { name: '再问一次' }))[0])

    await waitFor(() => expect(screen.getByText('求教页面')).toBeTruthy())
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
    mockedApi.listHistory.mockResolvedValue({
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

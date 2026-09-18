/** 「知识库」页面与接口的契约。
 *
 * 这一页的契约有四条，别的都是排版：
 *
 * 1. **双链是两个方向**——同一份数据既要说"我引了谁"，也要说"谁引了我"。
 *    反链可能为空，那不是错误，而是这本书还没被别的书写到。
 * 2. **点节点 = 聚焦，再点一次 = 回全图**——不需要额外的"取消"按钮。
 * 3. **只看书是一种有意义的视图**——隐藏主题之后剩下的正是经典互参结构。
 * 4. **边上的说明来自语料原文**，界面只负责显示，不许自己编一句。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Knowledge from '../pages/Knowledge'
import type { KbGraph, KbNodeDetail } from '../api/client'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: {
    kbGraph: vi.fn(),
    kbLocal: vi.fn(),
    kbNode: vi.fn(),
    kbSearch: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

const GRAPH: KbGraph = {
  nodes: [
    {
      id: 'book:01',
      kind: 'book',
      label: '甲书',
      degree: 2,
      meta: { book_id: '01', author: '作者甲', category: '哲学', chapter_count: 8, has_source: true },
    },
    {
      id: 'book:02',
      kind: 'book',
      label: '乙书',
      degree: 2,
      meta: { book_id: '02', author: '作者乙', category: '处世', chapter_count: 3, has_source: false },
    },
    { id: 'theme:谋略', kind: 'theme', label: '谋略', degree: 2, meta: { theme: '谋略' } },
  ],
  edges: [
    { source: 'book:01', target: 'theme:谋略', kind: 'theme', label: '以退为进', weight: 2 },
    { source: 'book:02', target: 'theme:谋略', kind: 'theme', label: '守拙', weight: 1 },
    { source: 'book:01', target: 'book:02', kind: 'cross', label: '两书同源。', weight: 1 },
  ],
  stats: { books: 2, themes: 1, edges: 3 },
}

const DETAIL: KbNodeDetail = {
  node: GRAPH.nodes[0],
  outgoing: [
    {
      node_id: 'theme:谋略',
      label: '谋略',
      kind: 'theme',
      edge_label: '以退为进',
      direction: 'out',
    },
    {
      node_id: 'book:02',
      label: '乙书',
      kind: 'cross',
      edge_label: '两书同源。',
      direction: 'out',
    },
  ],
  backlinks: [],
  theme_rows: [
    {
      theme: '谋略',
      book_id: '01',
      book_title: '甲书',
      judgment: '柔弱胜刚强，以退为进',
      quote: '"反者道之动"（40）',
    },
  ],
  cross_refs: [{ name: '乙书', detail: '两书同源。' }],
}

function renderPage() {
  return render(
    <MemoryRouter>
      <Knowledge />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.kbGraph.mockResolvedValue(GRAPH)
  mockedApi.kbLocal.mockResolvedValue(GRAPH)
  mockedApi.kbNode.mockResolvedValue(DETAIL)
  mockedApi.kbSearch.mockResolvedValue([])
})

describe('知识库页面', () => {
  it('标题与规模说明来自后端统计', async () => {
    renderPage()
    expect(screen.getByRole('heading', { name: '知识库' })).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByText('2 部经典 · 1 个主题 · 3 条关联')).toBeInTheDocument(),
    )
  })

  it('把节点画成可点的图元，并按类型命名', async () => {
    renderPage()
    expect(await screen.findByRole('button', { name: '甲书（经典）' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '乙书（经典）' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '谋略（主题）' })).toBeInTheDocument()
  })

  it('默认不含章节节点', async () => {
    renderPage()
    await screen.findByRole('button', { name: '甲书（经典）' })
    expect(mockedApi.kbGraph).toHaveBeenCalledWith(false)
  })

  it('展开章节会重新取图', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('button', { name: '甲书（经典）' })

    await user.click(screen.getByRole('button', { name: '展开章节' }))

    await waitFor(() => expect(mockedApi.kbGraph).toHaveBeenCalledWith(true))
  })

  it('只看书会隐藏主题节点', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('button', { name: '谋略（主题）' })

    await user.click(screen.getByRole('button', { name: '只看书' }))

    expect(screen.queryByRole('button', { name: '谋略（主题）' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '甲书（经典）' })).toBeInTheDocument()
  })

  it('没选中节点时只给提示，不请求详情', async () => {
    renderPage()
    await screen.findByRole('button', { name: '甲书（经典）' })
    expect(screen.getByText(/点图上的节点/)).toBeInTheDocument()
    expect(mockedApi.kbNode).not.toHaveBeenCalled()
  })

  it('点节点后同时取局部图与详情', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '甲书（经典）' }))

    await waitFor(() => expect(mockedApi.kbNode).toHaveBeenCalledWith('book:01'))
    expect(mockedApi.kbLocal).toHaveBeenCalledWith('book:01', false)
  })

  it('详情面板列出出链与反向链接两个方向', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '甲书（经典）' }))

    expect(await screen.findByText('出链 · 它引用了')).toBeInTheDocument()
    expect(screen.getByText('反向链接 · 谁引用了它')).toBeInTheDocument()
  })

  it('反链为空时说明原因，而不是留白', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '甲书（经典）' }))

    expect(await screen.findByText('还没有别的书写到它')).toBeInTheDocument()
  })

  it('边上的说明用原文，不做改写', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '甲书（经典）' }))
    await screen.findByText('出链 · 它引用了')

    // 主题边的说明、互参边的说明，都是语料里的原句
    expect(screen.getByText('以退为进')).toBeInTheDocument()
    expect(screen.getByText('两书同源。')).toBeInTheDocument()
    // 互参段还带着它对照的是哪一本
    expect(screen.getByText('与《乙书》')).toBeInTheDocument()
  })

  it('节点卡片显示书的元信息', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '甲书（经典）' }))

    expect(await screen.findByRole('heading', { name: '甲书' })).toBeInTheDocument()
    expect(screen.getByText('作者甲')).toBeInTheDocument()
    expect(screen.getByText('含原典全文')).toBeInTheDocument()
  })

  it('再点同一个节点回到全图', async () => {
    const user = userEvent.setup()
    renderPage()
    const node = await screen.findByRole('button', { name: '甲书（经典）' })
    await user.click(node)
    expect(await screen.findByRole('heading', { name: '甲书' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '甲书（经典）' }))

    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: '甲书' })).not.toBeInTheDocument(),
    )
    expect(screen.getByText(/点图上的节点/)).toBeInTheDocument()
  })

  it('「返回全图」按钮等价于再点一次', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '甲书（经典）' }))
    await screen.findByRole('heading', { name: '甲书' })

    await user.click(screen.getByRole('button', { name: '返回全图' }))

    await waitFor(() => expect(screen.getByText(/点图上的节点/)).toBeInTheDocument())
  })

  it('主题明细与互参原文都在卡片里', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '甲书（经典）' }))

    expect(await screen.findByText('在八个主题下')).toBeInTheDocument()
    expect(screen.getByText('柔弱胜刚强，以退为进')).toBeInTheDocument()
    expect(screen.getByText('"反者道之动"（40）')).toBeInTheDocument()
    expect(screen.getByText('写下的互参')).toBeInTheDocument()
  })

  it('书节点上有去阅读的入口', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '甲书（经典）' }))

    expect(await screen.findByRole('button', { name: '去阅读' })).toBeInTheDocument()
  })

  it('出链里的条目可以点，点了就切到那个节点', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '甲书（经典）' }))
    await screen.findByText('出链 · 它引用了')

    // 用边类型限定：图上那个节点按钮叫「乙书（经典）」，两者都会匹配 /乙书/
    await user.click(screen.getByRole('button', { name: /经典互参/ }))

    await waitFor(() => expect(mockedApi.kbNode).toHaveBeenCalledWith('book:02'))
  })

  it('读取失败时给红色说明而不是空白页', async () => {
    mockedApi.kbGraph.mockRejectedValue(new Error('boom'))
    renderPage()
    expect(await screen.findByText(/读不到知识库/)).toBeInTheDocument()
  })

  it('筛选后没有任何节点时给出说明', async () => {
    mockedApi.kbGraph.mockResolvedValue({
      nodes: [{ id: 'theme:谋略', kind: 'theme', label: '谋略', degree: 0, meta: {} }],
      edges: [],
      stats: { books: 0, themes: 1, edges: 0 },
    })
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('button', { name: '谋略（主题）' })

    await user.click(screen.getByRole('button', { name: '只看书' }))

    expect(screen.getByText('这个筛选下没有节点')).toBeInTheDocument()
  })
})

describe('按名字找节点', () => {
  it('空结果给出提示', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('button', { name: '甲书（经典）' })

    await user.type(screen.getByLabelText('查找节点'), '山海经')
    await user.click(screen.getByRole('button', { name: '查找' }))

    expect(await screen.findByText('没有匹配的节点')).toBeInTheDocument()
  })

  it('命中后点结果即聚焦该节点', async () => {
    mockedApi.kbSearch.mockResolvedValue([
      { id: 'book:02', kind: 'book', label: '乙书', degree: 2, meta: { book_id: '02' } },
    ])
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('button', { name: '甲书（经典）' })

    await user.type(screen.getByLabelText('查找节点'), '乙')
    await user.click(screen.getByRole('button', { name: '查找' }))
    // 限定在搜索区里点：图上那个节点按钮的名字里也有"乙书"
    await user.click(
      await within(screen.getByRole('search')).findByRole('button', { name: /乙书/ }),
    )

    await waitFor(() => expect(mockedApi.kbNode).toHaveBeenCalledWith('book:02'))
  })

  it('检索失败不会把整页炸掉', async () => {
    mockedApi.kbSearch.mockRejectedValue(new Error('boom'))
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('button', { name: '甲书（经典）' })

    await user.type(screen.getByLabelText('查找节点'), '甲')
    await user.click(screen.getByRole('button', { name: '查找' }))

    expect(await screen.findByText(/读不到知识库/)).toBeInTheDocument()
  })
})

/** 「画像」页面。
 *
 * 这一页的契约有五条，别的都是排版：
 *
 * 1. **特征按分类挂在人形两侧**——分类是后端给的封闭集合，每条特征都带着
 *    "依据"。画像最怕"它凭什么这么说"，那句话就是答案，不能省。
 * 2. **归纳、评定人物都是异步的，不能挡住首屏**——进页面先渲染已有的画像；
 *    发现"问过话但还没归纳过"才在后台补一次，且**只补一次**（否则归纳完重新
 *    读取会再触发一轮，变成死循环）。
 * 3. **两次模型调用要串起来**：归纳在前、评人在后。并行发出去不只是让上游吃
 *    两份负载，更糟的是会拿**旧画像**去评人——刚归纳出来的特征还没进库。
 * 4. **没有特征不等于出错**——没有提问、模型不可用、模型没读出东西，各自说明
 *    原因，不要弹红色报错。
 * 5. **形象可选男女，切换存后端**——它属于画像这份数据，不是浏览器本地偏好。
 *    两式是**两幅不同的古画**（陈洪绶《仿古图册》），各自带署名；这条契约掉了，
 *    多半是有人把它们合并成"一张图换个色"了。男女开关**同时是评选的池子**，
 *    所以切过去要重读一次画像，不能只在本地把开关拨过去。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Profile from '../pages/Profile'
import type {
  ExtractResult,
  FigureInfo,
  FigureResult,
  ProfileResponse,
  TraitItem,
} from '../api/client'
import { api } from '../api/client'
import { I18nProvider } from '../i18n'

vi.mock('../api/client', () => ({
  api: {
    getProfile: vi.fn(),
    extractProfile: vi.fn(),
    evaluateFigure: vi.fn(),
    setAvatar: vi.fn(),
    deleteTrait: vi.fn(),
    clearProfile: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

const TRAITS: TraitItem[] = [
  {
    id: 1,
    category: '性格',
    content: '做事偏谨慎，习惯想清楚再动手',
    evidence: '我说我总是犹豫很久才决定',
    confidence: 0.8,
  },
  {
    id: 2,
    category: '性格',
    content: '在意别人怎么看自己',
    evidence: '我说我怕别人觉得我不行',
    confidence: 0.6,
  },
  { id: 3, category: '专业', content: '做软件相关的工作', evidence: '我说我在改一个接口', confidence: 0.5 },
  { id: 4, category: '规划', content: '想换个行业', evidence: '我说我想转行', confidence: 0.4 },
]

const CATEGORIES = ['性格', '年龄', '爱好', '生活条件', '成熟度', '专业', '规划']

/** 「最像你的一位历史人物」。默认是空的——还没评过，画框里还是那页册页。 */
function figure(overrides: Partial<FigureInfo> = {}): FigureInfo {
  return {
    id: '',
    name: '',
    era: '',
    blurb: '',
    reason: '',
    credit: '',
    portrait: '',
    week: '',
    chosen_at: '',
    pool_size: 24,
    needs_refresh: false,
    ...overrides,
  }
}

/** 评出来的一位：陶渊明。 */
const TAO = figure({
  id: 'taoyuanming',
  name: '陶渊明',
  era: '东晋',
  blurb: '不为五斗米折腰，归去来兮。',
  reason: '你也不爱应酬，喜欢一个人待着；想问题也偏往前看。',
  credit: '佚名《陶渊明像》',
  portrait: '/api/profile/figure/portrait/taoyuanming',
  week: '2026-W38',
  chosen_at: '2026-09-17',
})

/** 英文界面下的那一位（名字与理由都由后端按语言给）。 */
const TAO_EN = figure({
  ...TAO,
  name: 'Tao Yuanming',
  era: 'Eastern Jin',
  blurb: 'He would not bow for five pecks of rice.',
  reason: 'You shun company too, and you would rather keep to yourself.',
  credit: 'Anonymous, Portrait of Tao Yuanming',
})

function profile(overrides: Partial<ProfileResponse> = {}): ProfileResponse {
  return {
    available: true,
    error: '',
    avatar: 'male',
    total: TRAITS.length,
    traits: TRAITS,
    categories: CATEGORIES,
    pending: 0,
    figure: figure(),
    ...overrides,
  }
}

const NOTHING_NEW: ExtractResult = {
  ok: false,
  extracted: 0,
  total: TRAITS.length,
  llm_used: true,
  error: 'nothing_usable',
}

const PICKED: FigureResult = { ok: true, id: 'taoyuanming', llm_used: true, error: '' }

/** 手动控制的 Promise：用来在"还没回来"的那一刻做断言。 */
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => {
    resolve = done
  })
  return { promise, resolve }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.getProfile.mockResolvedValue(profile())
  mockedApi.extractProfile.mockResolvedValue({
    ok: true,
    extracted: 1,
    total: TRAITS.length + 1,
    llm_used: true,
    error: '',
  })
  mockedApi.evaluateFigure.mockResolvedValue(PICKED)
  mockedApi.setAvatar.mockResolvedValue({ avatar: 'female' })
  mockedApi.deleteTrait.mockResolvedValue({ deleted: 1 })
  mockedApi.clearProfile.mockResolvedValue({ deleted: TRAITS.length })
})

function renderProfile() {
  return render(<Profile />)
}

describe('画像的内容', () => {
  it('把特征按分类挂出来，并写明依据', async () => {
    renderProfile()

    await waitFor(() => expect(screen.getByText('做事偏谨慎，习惯想清楚再动手')).toBeTruthy())
    // 分类标题（英文界面下会译，中文界面原样）
    expect(screen.getByRole('heading', { name: '性格' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: '专业' })).toBeTruthy()
    // 依据不能省——画像最怕"它凭什么这么说"
    expect(screen.getByText('依据：我说我总是犹豫很久才决定')).toBeTruthy()
    // 模型的把握程度也如实写出来
    expect(screen.getByText('把握 80%')).toBeTruthy()
  })

  it('同一分类下的多条特征都列出来', async () => {
    renderProfile()

    await waitFor(() => expect(screen.getByText('在意别人怎么看自己')).toBeTruthy())
    expect(screen.getAllByRole('heading', { name: '性格' })).toHaveLength(1)
  })

  it('说明共有多少条特征', async () => {
    renderProfile()

    await waitFor(() => expect(screen.getByText(/共 4 条特征/)).toBeTruthy())
  })

  it('给出人形，切换男女时界面跟着变', async () => {
    const user = userEvent.setup()
    renderProfile()

    const figure = await screen.findByRole('img', { name: '你的形象' })
    expect(figure).toBeTruthy()

    const male = screen.getByRole('button', { name: '男' })
    expect(male.getAttribute('aria-pressed')).toBe('true')

    // 换册页就是换名录：切过去之后要重读一次画像（后端会把那一册的人带回来）
    mockedApi.getProfile.mockResolvedValueOnce(profile({ avatar: 'female' }))
    await user.click(screen.getByRole('button', { name: '女' }))

    // 切换要存到后端：它属于画像这份数据，不是浏览器本地偏好
    await waitFor(() => expect(mockedApi.setAvatar).toHaveBeenCalledWith('female'))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '女' }).getAttribute('aria-pressed')).toBe(
        'true',
      ),
    )
    expect(mockedApi.getProfile).toHaveBeenCalledTimes(2)
  })

  it('两式换的是画本身，署名也跟着换', async () => {
    const user = userEvent.setup()
    renderProfile()

    // 男女两式是两幅不同的古画，不是同一张图换个色——这条掉了就说明被人合并了
    const srcOf = () => screen.getByRole('img', { name: '你的形象' }).getAttribute('src')
    const maleSrc = (await screen.findByRole('img', { name: '你的形象' })).getAttribute('src')
    expect(maleSrc).toBeTruthy()
    expect(screen.getByText(/陈洪绶《仿古图册·陶渊明像》/)).toBeTruthy()

    mockedApi.getProfile.mockResolvedValueOnce(profile({ avatar: 'female' }))
    await user.click(screen.getByRole('button', { name: '女' }))

    await waitFor(() => expect(srcOf()).not.toBe(maleSrc))
    // 古画不是"素材"，署名与藏地要跟着走
    expect(screen.getByText(/陈洪绶《仿古图册·仕女》/)).toBeTruthy()
    expect(screen.getByText('克利夫兰艺术博物馆藏')).toBeTruthy()
  })
})

describe('归纳', () => {
  it('没有待归纳的新提问时不去打扰模型', async () => {
    renderProfile()

    await waitFor(() => expect(screen.getByText(/共 4 条特征/)).toBeTruthy())
    expect(mockedApi.extractProfile).not.toHaveBeenCalled()
  })

  it('有待归纳的新提问时后台自动补一次', async () => {
    const pending = deferred<ExtractResult>()
    mockedApi.getProfile.mockResolvedValue(profile({ pending: 3 }))
    mockedApi.extractProfile.mockReturnValue(pending.promise)

    renderProfile()

    // 归纳要几十秒，先说清楚在做什么，别让人以为页面卡住了。
    // 这一刻模型还没回来，所以拿一个手动控制的 Promise 顶住。
    await waitFor(() => expect(screen.getByText(/已经问过 3 条/)).toBeTruthy())

    pending.resolve({ ok: true, extracted: 1, total: 5, llm_used: true, error: '' })
    await waitFor(() => expect(screen.getByText('新增 1 条特征')).toBeTruthy())
  })

  it('自动归纳只做一次，不会自己转圈', async () => {
    mockedApi.getProfile.mockResolvedValue(profile({ pending: 2 }))
    renderProfile()

    await waitFor(() => expect(mockedApi.extractProfile).toHaveBeenCalledTimes(1))
    // 归纳完会重新读取画像；若这时又触发一轮，就成了死循环
    await waitFor(() => expect(mockedApi.getProfile).toHaveBeenCalledTimes(2))
    expect(mockedApi.extractProfile).toHaveBeenCalledTimes(1)
  })

  it('手动点「重新归纳」也会归纳一次', async () => {
    const user = userEvent.setup()
    renderProfile()
    await waitFor(() => expect(screen.getByText(/共 4 条特征/)).toBeTruthy())

    await user.click(screen.getByRole('button', { name: '重新归纳' }))

    await waitFor(() => expect(mockedApi.extractProfile).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(mockedApi.getProfile).toHaveBeenCalledTimes(2))
  })

  it('模型没读出东西时说清楚，而不是装作新增了', async () => {
    mockedApi.extractProfile.mockResolvedValue(NOTHING_NEW)
    const user = userEvent.setup()
    renderProfile()
    await waitFor(() => expect(screen.getByText(/共 4 条特征/)).toBeTruthy())

    await user.click(screen.getByRole('button', { name: '重新归纳' }))

    await waitFor(() => expect(screen.getByText(/这次没读出新的特征/)).toBeTruthy())
  })

  it('没有提问时告诉用户先去求教，而不是弹报错', async () => {
    mockedApi.extractProfile.mockResolvedValue({
      ok: false,
      extracted: 0,
      total: 0,
      llm_used: false,
      error: 'no_records',
    })
    const user = userEvent.setup()
    renderProfile()
    await waitFor(() => expect(screen.getByText(/共 4 条特征/)).toBeTruthy())

    await user.click(screen.getByRole('button', { name: '重新归纳' }))

    await waitFor(() => expect(screen.getByText(/还没有求教记录/)).toBeTruthy())
  })

  it('没有可用模型时如实说明', async () => {
    mockedApi.extractProfile.mockResolvedValue({
      ok: false,
      extracted: 0,
      total: 0,
      llm_used: false,
      error: 'llm_disabled',
    })
    const user = userEvent.setup()
    renderProfile()
    await waitFor(() => expect(screen.getByText(/共 4 条特征/)).toBeTruthy())

    await user.click(screen.getByRole('button', { name: '重新归纳' }))

    await waitFor(() => expect(screen.getByText(/没有可用的模型/)).toBeTruthy())
  })

  it('上游报错时把原文说出来，比兜底话有用', async () => {
    mockedApi.extractProfile.mockResolvedValue({
      ok: false,
      extracted: 0,
      total: 0,
      llm_used: false,
      error: 'HTTP 503：全挂了',
    })
    const user = userEvent.setup()
    renderProfile()
    await waitFor(() => expect(screen.getByText(/共 4 条特征/)).toBeTruthy())

    await user.click(screen.getByRole('button', { name: '重新归纳' }))

    await waitFor(() => expect(screen.getByText(/HTTP 503/)).toBeTruthy())
  })
})

describe('画像的删除', () => {
  it('删掉一条特征，计数同时跟着减', async () => {
    const user = userEvent.setup()
    renderProfile()
    await waitFor(() => expect(screen.getByText('做事偏谨慎，习惯想清楚再动手')).toBeTruthy())

    await user.click(screen.getAllByRole('button', { name: '删掉这条' })[0])

    await waitFor(() => expect(mockedApi.deleteTrait).toHaveBeenCalledWith(1))
    await waitFor(() => expect(screen.queryByText('做事偏谨慎，习惯想清楚再动手')).toBeNull())
    // 界面上不能自相矛盾
    expect(screen.getByText(/共 3 条特征/)).toBeTruthy()
  })

  it('清空要先确认，取消则不动', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    renderProfile()

    await user.click(await screen.findByRole('button', { name: '清空画像' }))

    expect(confirm).toHaveBeenCalled()
    expect(mockedApi.clearProfile).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('确认后清空并重新读取', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderProfile()

    await user.click(await screen.findByRole('button', { name: '清空画像' }))

    await waitFor(() => expect(mockedApi.clearProfile).toHaveBeenCalled())
    // 以服务端为准，不靠本地把数组清掉
    await waitFor(() => expect(mockedApi.getProfile).toHaveBeenCalledTimes(2))
    confirm.mockRestore()
  })

  it('没有特征时不显示清空按钮', async () => {
    mockedApi.getProfile.mockResolvedValue(profile({ traits: [], total: 0 }))
    renderProfile()

    await waitFor(() => expect(screen.getByText(/还没有归纳出任何特征/)).toBeTruthy())
    expect(screen.queryByRole('button', { name: '清空画像' })).toBeNull()
  })
})

describe('最像你的一位历史人物', () => {
  it('还没评出人来时，画框里还是那页册页', async () => {
    renderProfile()

    await waitFor(() => expect(screen.getByRole('img', { name: '你的形象' })).toBeTruthy())
    // 空着比放一个陌生人好；题跋也不该提前出现
    expect(screen.queryByText('像在哪里')).toBeNull()
    expect(mockedApi.evaluateFigure).not.toHaveBeenCalled()
  })

  it('评出来之后，画框里换成那个人，题签写着是谁', async () => {
    mockedApi.getProfile.mockResolvedValue(profile({ figure: TAO }))
    renderProfile()

    const portrait = await screen.findByRole('img', { name: '陶渊明' })
    expect(portrait.getAttribute('src')).toBe('/api/profile/figure/portrait/taoyuanming')

    // 题签：先说是谁、哪个时代、一句话，再落署名
    expect(screen.getByText('最像你的一位')).toBeTruthy()
    expect(screen.getByText('陶渊明')).toBeTruthy()
    expect(screen.getByText('东晋 · 不为五斗米折腰，归去来兮。')).toBeTruthy()
    expect(screen.getByText('佚名《陶渊明像》')).toBeTruthy()

    // 题跋：像在哪里
    expect(screen.getByRole('heading', { name: '像在哪里' })).toBeTruthy()
    expect(screen.getByText(/你也不爱应酬，喜欢一个人待着/)).toBeTruthy()
    expect(screen.getByText('2026-09-17 从 24 位候选人中选出')).toBeTruthy()
  })

  it('该评的时候后台自己去评一次，评完把新的人读回来', async () => {
    mockedApi.getProfile
      .mockResolvedValueOnce(profile({ figure: figure({ needs_refresh: true }) }))
      .mockResolvedValueOnce(profile({ figure: TAO }))

    renderProfile()

    await waitFor(() => expect(mockedApi.evaluateFigure).toHaveBeenCalledTimes(1))
    // 中文界面就按中文评
    expect(mockedApi.evaluateFigure).toHaveBeenCalledWith('zh')
    await waitFor(() => expect(screen.getByRole('img', { name: '陶渊明' })).toBeTruthy())
  })

  it('刚评过、画像也没变时不去打扰模型', async () => {
    mockedApi.getProfile.mockResolvedValue(profile({ figure: TAO }))
    renderProfile()

    await waitFor(() => expect(screen.getByRole('img', { name: '陶渊明' })).toBeTruthy())
    // 一周之内答案不变——这正是"每周更新"的含义
    expect(mockedApi.evaluateFigure).not.toHaveBeenCalled()
  })

  it('自动评定只做一次，不会自己转圈', async () => {
    mockedApi.getProfile
      .mockResolvedValueOnce(profile({ figure: figure({ needs_refresh: true }) }))
      .mockResolvedValue(profile({ figure: TAO }))

    renderProfile()

    await waitFor(() => expect(mockedApi.evaluateFigure).toHaveBeenCalledTimes(1))
    // 评完会重新读取画像；若这时又触发一轮，就成了死循环
    await waitFor(() => expect(mockedApi.getProfile).toHaveBeenCalledTimes(2))
    expect(mockedApi.evaluateFigure).toHaveBeenCalledTimes(1)
  })

  it('归纳与评定串着来：归纳没回来就不去评人', async () => {
    const extracting = deferred<ExtractResult>()
    // 归纳完 pending 归零，但画像里的人还没评出来（autoFigureRan 还等着）
    mockedApi.getProfile
      .mockResolvedValueOnce(profile({ pending: 3, figure: figure({ needs_refresh: true }) }))
      .mockResolvedValueOnce(profile({ pending: 0, figure: figure({ needs_refresh: true }) }))
      .mockResolvedValue(profile({ figure: TAO }))
    mockedApi.extractProfile.mockReturnValue(extracting.promise)

    renderProfile()

    await waitFor(() => expect(screen.getByText(/已经问过 3 条/)).toBeTruthy())
    // 并行发出去不只是让上游吃两份负载，更糟的是会拿**旧画像**去评人
    expect(mockedApi.evaluateFigure).not.toHaveBeenCalled()

    extracting.resolve({ ok: true, extracted: 1, total: 5, llm_used: true, error: '' })
    await waitFor(() => expect(mockedApi.evaluateFigure).toHaveBeenCalledTimes(1))
  })

  it('手动点「重新评定」也会评一次', async () => {
    const user = userEvent.setup()
    mockedApi.getProfile.mockResolvedValue(profile({ figure: TAO }))
    renderProfile()
    await waitFor(() => expect(screen.getByRole('img', { name: '陶渊明' })).toBeTruthy())

    await user.click(screen.getByRole('button', { name: '重新评定' }))

    await waitFor(() => expect(mockedApi.evaluateFigure).toHaveBeenCalledTimes(1))
  })

  it('评不出来时说清楚原因，而不是弹一个红框了事', async () => {
    const user = userEvent.setup()
    mockedApi.getProfile.mockResolvedValue(profile({ figure: TAO }))
    mockedApi.evaluateFigure.mockResolvedValue({
      ok: false,
      id: '',
      llm_used: false,
      error: 'llm_disabled',
    })
    renderProfile()
    await waitFor(() => expect(screen.getByRole('img', { name: '陶渊明' })).toBeTruthy())

    await user.click(screen.getByRole('button', { name: '重新评定' }))

    await waitFor(() => expect(screen.getByText(/没有可用的模型/)).toBeTruthy())
    // 上一次评出来的人还在，不该因为一次失败就把他抹掉
    expect(screen.getByText('陶渊明')).toBeTruthy()
  })

  it('模型给的名字不在名录里时如实说', async () => {
    const user = userEvent.setup()
    mockedApi.getProfile.mockResolvedValue(profile({ figure: TAO }))
    mockedApi.evaluateFigure.mockResolvedValue({
      ok: false,
      id: '',
      llm_used: true,
      error: 'not_in_pool',
    })
    renderProfile()
    await waitFor(() => expect(screen.getByRole('img', { name: '陶渊明' })).toBeTruthy())

    await user.click(screen.getByRole('button', { name: '重新评定' }))

    await waitFor(() => expect(screen.getByText(/不在名录里/)).toBeTruthy())
  })

  it('名录空着时说一声，而不是让人以为还没做完', async () => {
    mockedApi.getProfile.mockResolvedValue(profile({ figure: figure({ pool_size: 0 }) }))
    renderProfile()

    await waitFor(() =>
      expect(screen.getByText('这一册名录里还没有人。')).toBeTruthy(),
    )
    expect(mockedApi.evaluateFigure).not.toHaveBeenCalled()
  })

  it('换到另一册时重读画像，并把评定重新交给后台', async () => {
    const user = userEvent.setup()
    mockedApi.getProfile
      .mockResolvedValueOnce(profile({ figure: TAO }))
      .mockResolvedValueOnce(profile({ avatar: 'female', figure: figure({ needs_refresh: true }) }))
      .mockResolvedValue(profile({ avatar: 'female', figure: figure({ ...TAO, name: '李清照', id: 'liqingzhao' }) }))
    mockedApi.evaluateFigure.mockResolvedValue({ ok: true, id: 'liqingzhao', llm_used: true, error: '' })

    renderProfile()
    await waitFor(() => expect(screen.getByRole('img', { name: '陶渊明' })).toBeTruthy())

    await user.click(screen.getByRole('button', { name: '女' }))

    // 两边是两份名录、两个人，切过去得让服务端来说
    await waitFor(() => expect(mockedApi.evaluateFigure).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.getByRole('img', { name: '李清照' })).toBeTruthy())
  })
})

describe('数据库不可用', () => {
  const BROKEN: ProfileResponse = {
    available: false,
    error: 'OperationalError: attempt to write a readonly database',
    avatar: 'male',
    total: 0,
    traits: [],
    categories: CATEGORIES,
    pending: 0,
    figure: figure(),
  }

  it('说明原因，而不是谎称"还没有特征"', async () => {
    mockedApi.getProfile.mockResolvedValue(BROKEN)
    renderProfile()

    await waitFor(() => expect(screen.getByText(/readonly database/)).toBeTruthy())
    expect(screen.queryByText(/还没有归纳出任何特征/)).toBeNull()
    // 讲清楚影响范围，免得用户以为整个应用坏了
    expect(screen.getByText(/问答记录与其它功能不受影响/)).toBeTruthy()
    // 库都不可用就别去调模型了
    expect(mockedApi.extractProfile).not.toHaveBeenCalled()
  })
})

describe('英文界面', () => {
  /** 语言存在 localStorage 里，Provider 挂载时读它。 */
  function renderEnglish() {
    window.localStorage.setItem('rsds.lang', 'en')
    return render(
      <I18nProvider>
        <Profile />
      </I18nProvider>,
    )
  }

  it('分类标签译成英文——它们来自后端的封闭集合，界面负责译', async () => {
    renderEnglish()

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Character' })).toBeTruthy())
    expect(screen.getByRole('heading', { name: 'Profession' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Plans' })).toBeTruthy()
    // 中文分类名不该漏出来
    expect(screen.queryByRole('heading', { name: '性格' })).toBeNull()
  })

  it('页面自己的文案也跟着换，不夹中文', async () => {
    renderEnglish()

    await waitFor(() => expect(screen.getByRole('button', { name: 'Read them again' })).toBeTruthy())
    expect(screen.getByRole('button', { name: 'Female' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Male' })).toBeTruthy()
    expect(screen.getByText('Because: 我说我总是犹豫很久才决定')).toBeTruthy()
    expect(screen.getByText('80% sure')).toBeTruthy()
    expect(screen.getByText(/4 traits in all/)).toBeTruthy()
    expect(screen.queryByText(/共 4 条特征/)).toBeNull()
    // 画的署名也要译，否则英文界面里会冒出一行中文
    expect(screen.getByText(/Chen Hongshou/)).toBeTruthy()
    expect(screen.queryByText(/陈洪绶/)).toBeNull()
  })

  it('英文界面里归纳，请求带上 en——特征正文才会是英文', async () => {
    const user = userEvent.setup()
    renderEnglish()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Read them again' })).toBeTruthy())

    await user.click(screen.getByRole('button', { name: 'Read them again' }))

    await waitFor(() => expect(mockedApi.extractProfile).toHaveBeenCalledWith('en'))
  })

  it('评出来的人也译过来，理由与候选人计数都不夹中文', async () => {
    mockedApi.getProfile.mockResolvedValue(profile({ figure: TAO_EN }))
    renderEnglish()

    expect(await screen.findByRole('img', { name: 'Tao Yuanming' })).toBeTruthy()
    expect(screen.getByText('The one you most resemble')).toBeTruthy()
    expect(screen.getByText('Eastern Jin · He would not bow for five pecks of rice.')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Where the likeness lies' })).toBeTruthy()
    expect(screen.getByText('Chosen 2026-09-17, from 24 candidates')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Judge it again' })).toBeTruthy()
    expect(screen.queryByText('陶渊明')).toBeNull()
  })

  it('英文界面里评定，请求带上 en——名字与理由才会是英文', async () => {
    const user = userEvent.setup()
    mockedApi.getProfile.mockResolvedValue(profile({ figure: TAO_EN }))
    renderEnglish()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Judge it again' })).toBeTruthy(),
    )

    await user.click(screen.getByRole('button', { name: 'Judge it again' }))

    await waitFor(() => expect(mockedApi.evaluateFigure).toHaveBeenCalledWith('en'))
  })
})

/** 界面文案字典与术语表。
 *
 * 这里只放"我们写的字"——导航、按钮、提示、空态、错误说明。
 * 语料本身（古籍原文、深读笔记、金句释义、章节名）仍然是中文，
 * 它们是这套产品的**内容**而不是界面：翻译它们等于重新做一套语料。
 * 因此英文界面下这些位置保持原样，只把"书的封面信息"（书名、作者、类目、
 * 主题）与检索结果的出处标注一并译出，让人至少知道自己在看哪本书。
 *
 * 键用点号分组的扁平字符串，而不是嵌套对象：嵌套要写一整套取值器，
 * 扁平键配 `keyof typeof ZH` 就能拿到"漏译即编译报错"的检查。
 */

export type Lang = 'zh' | 'en'

export const LANGS: readonly Lang[] = ['zh', 'en']

/** 兜底语言。没有 Provider（例如单测直接渲染某个页面）时一律用它。 */
export const DEFAULT_LANG: Lang = 'zh'

/** 中文文案。它同时是键的**唯一来源**——加键先加在这里。 */
const ZH = {
  // ── 顶栏 / 页脚 ──────────────────────────────────────────────
  'app.subtitle': '经典智慧知识库',
  'app.footer': '人生导师 · 中国传统经典智慧知识库',
  'nav.label': '主导航',
  'nav.library': '书架',
  'nav.search': '寻章',
  'nav.ask': '求教',
  'nav.history': '回响',
  'nav.insights': '感悟',
  'lang.group': '切换界面语言',
  'lang.zh': '中文',
  'lang.en': 'EN',

  // ── 通用 ────────────────────────────────────────────────────
  'status.loading': '加载中…',
  'error.requestFailed': '请求失败（{status}）',

  // ── 书架 ────────────────────────────────────────────────────
  'library.title': '书架',
  'library.description': '{count} 部经典 · 点击进入阅读',
  'library.all': '全部',
  'library.chapters': '{count} 章',
  'library.noContent': '暂无内容',
  'library.hasSource': ' · 含原典',
  'library.empty': '书架还是空的',
  'library.emptyCategory': '该分类下暂无书目',

  // ── 寻章 ────────────────────────────────────────────────────
  'search.title': '寻章',
  'search.description': '在全部经典的深读笔记与原典全文中检索一句话，直接跳到它所在的位置',
  'search.placeholder': '输入关键词，例如：上善若水',
  'search.keywordLabel': '检索关键词',
  'search.scopeGroup': '检索范围',
  'search.submit': '检索',
  'search.kind.all': '全部',
  'search.kind.notes': '深读笔记',
  'search.kind.source': '原典全文',
  'search.badge.source': '原典',
  'search.badge.notes': '笔记',
  'search.examplesTitle': '试试这些关键词：',
  'search.searching': '正在翻检经典…',
  'search.hits': '命中 {count} 段',
  'search.noHits': '没有找到相关段落，换个词试试',
  'search.score': '相关度 {score}',
  'search.failed': '检索失败，请稍后再试',

  // ── 阅读 ────────────────────────────────────────────────────
  'reader.back': '← 书架',
  'reader.tab.notes': '理解笔记',
  'reader.tab.source': '原典全文',
  'reader.chapterList': '章节列表',
  'reader.viewGroup': '阅读内容',
  'reader.chapterCount': '共 {count} 章',
  'reader.noChapters': '暂无章节',
  'reader.pickChapter': '选择左侧章节开始阅读',
  'reader.notFound': '未找到此书',
  'reader.loadingSource': '加载原典…',
  'reader.startAt': '从第 {offset} 字处开始显示',
  'reader.fromStart': '从头读',
  'reader.progress': '已载入 {loaded} / {total} 字',
  'reader.loading': '载入中…',
  'reader.loadMore': '载入后续',

  // ── 求教 ────────────────────────────────────────────────────
  'ask.title': '求教',
  'ask.description': '向人生导师讲述你的问题或困境，它会从经典智慧中寻找答案',
  'ask.modelButton': '模型：{mode}',
  'ask.model.default': '默认',
  'ask.model.custom': '自定义',
  'ask.model.incomplete': '未填写',
  'ask.suggestionsTitle': '说说你的困惑，例如：',
  'ask.suggestionsHint': '示例可以直接点；也可以用自己的话描述处境。',
  'ask.cited': '引用 {count} 段经典',
  'ask.aiAnswer': 'AI 深度解读 · {model}',
  'ask.localMode': '本地检索模式',
  'ask.saved': '已存入回响',
  'ask.thinking': '正在翻阅经典…',
  'ask.placeholder': '输入你的问题或困境…',
  'ask.inputLabel': '你的问题或困境',
  'ask.submit': '求教',
  'ask.composerHint': 'Enter 直接发送 · Shift + Enter 换行',
  'ask.failed': '请求失败，请稍后再试',

  // ── 回响 ────────────────────────────────────────────────────
  'history.title': '回响',
  'history.description': '问过的困惑与得到的回答都收在这里，只留最近半个月',
  'history.clear': '清空',
  'history.total': '共 {count} 条',
  'history.retention': '只保留最近 {days} 天',
  'history.nextPurge': '下次自动清理 {day}',
  'history.dbPath': '记录存放在 {path}',
  'history.unavailable':
    '历史记录暂时用不了：{error}。「求教」等其它功能不受影响，只是这次的问答不会被记下来。',
  'history.loading': '正在翻找旧日的问答…',
  'history.empty': '还没有求教记录，去「求教」问一个困惑试试',
  'history.cited': '引用 {count} 段经典',
  'history.aiAnswer': 'AI 深度解读 · {model}',
  'history.localMode': '本地检索模式',
  'history.askAgain': '再问一次',
  'history.delete': '删除',
  'history.loadMoreBusy': '读取中…',
  'history.loadMore': '加载更多（还有 {count} 条）',
  'history.confirmClear': '确定要清空全部历史记录吗？此操作不可撤销。',
  'history.loadFailed': '读取历史记录失败',
  'history.loadMoreFailed': '读取更多记录失败',
  'history.deleteFailed': '删除失败',
  'history.clearFailed': '清空失败',
  'history.justNow': '刚刚',
  'history.minutesAgo': '{count} 分钟前',
  'history.hoursAgo': '{count} 小时前',
  'history.daysAgo': '{count} 天前',
  'history.noDate': '——',

  // ── 感悟 ────────────────────────────────────────────────────
  'insight.title': '感悟',
  'insight.description': '每日一句经典智慧，给生活一点提醒',
  'insight.daily': '今日感悟',
  'insight.random': '随机一则',
  'insight.byTheme': '按主题浏览',
  'insight.all': '全部',
  'insight.pickTheme': '选择一个主题，看看不同的经典怎么说',
  'insight.emptyTheme': '该主题下暂无感悟',

  // ── 模型设置 ────────────────────────────────────────────────
  'model.default': '默认模型',
  'model.custom': '自定义模型',
  'model.needFields': '请先填写接口地址与 API Key',
  'model.connected': '连接成功，当前使用 {model}',
  'model.unreachable': '连不上这个地址',
  'model.requestFailed': '请求失败，请稍后再试',
  'model.testing': '正在连接…',
  'model.test': '测试连接',
  'model.defaultHint':
    '使用应用自带的模型配置，开箱即用。若想接自己的模型（例如公司的私有部署、或另一个服务商的 Key），切到「自定义模型」。',
  'model.baseUrl': '接口地址',
  'model.baseUrlHint': 'OpenAI 兼容接口的根地址，末尾的 /v1 要带上。',
  'model.apiKey': 'API Key',
  'model.apiKeyHint': '只保存在这台电脑的浏览器里，不会上传到别处，也不会写进程序文件。',
  'model.modelName': '模型名（可留空）',
  'model.modelPlaceholder': '留空则自动挑选',
  'model.modelHint':
    '留空时程序会从该地址可用的模型里挑一个能出字的，坏了会自动换下一个；填了就只用这一个——它不可用时会退回本地检索，不会悄悄换成别的模型。',
  'model.okModels': '（该地址提供 {count} 个模型）',
  'model.failModels': '（该地址提供了 {count} 个模型，但没一个能出字）',
  'model.incompleteHint':
    '接口地址与 API Key 都填上之后，「求教」才会走这个模型；在此之前仍用默认模型。',
} as const

export type MessageKey = keyof typeof ZH

/** 英文文案。类型是 `Record<MessageKey, string>`——**漏一条就编译不过**。 */
const EN: Record<MessageKey, string> = {
  'app.subtitle': 'Wisdom of the Classics',
  'app.footer': '人生导师 · A treasury of classical Chinese wisdom',
  'nav.label': 'Main navigation',
  'nav.library': 'Library',
  'nav.search': 'Search',
  'nav.ask': 'Ask',
  'nav.history': 'Echoes',
  'nav.insights': 'Insights',
  'lang.group': 'Interface language',
  'lang.zh': '中文',
  'lang.en': 'EN',

  'status.loading': 'Loading…',
  'error.requestFailed': 'Request failed ({status})',

  'library.title': 'Library',
  'library.description': '{count} classics · open one to read',
  'library.all': 'All',
  'library.chapters': '{count} chapters',
  'library.noContent': 'No content yet',
  'library.hasSource': ' · with source text',
  'library.empty': 'The shelf is still empty',
  'library.emptyCategory': 'Nothing in this category',

  'search.title': 'Search',
  'search.description':
    'Search a phrase across every deep-reading note and every source text, then jump straight to where it appears',
  'search.placeholder': 'Enter a Chinese keyword, e.g. 上善若水',
  'search.keywordLabel': 'Search keyword',
  'search.scopeGroup': 'Search scope',
  'search.submit': 'Search',
  'search.kind.all': 'All',
  'search.kind.notes': 'Reading notes',
  'search.kind.source': 'Source text',
  'search.badge.source': 'Source',
  'search.badge.notes': 'Notes',
  'search.examplesTitle': 'Try one of these keywords:',
  'search.searching': 'Turning the pages…',
  'search.hits': '{count} passages found',
  'search.noHits': 'No matching passage — try another keyword',
  'search.score': 'Score {score}',
  'search.failed': 'Search failed, please try again later',

  'reader.back': '← Library',
  'reader.tab.notes': 'Reading notes',
  'reader.tab.source': 'Source text',
  'reader.chapterList': 'Chapters',
  'reader.viewGroup': 'Reading view',
  'reader.chapterCount': '{count} chapters',
  'reader.noChapters': 'No chapters yet',
  'reader.pickChapter': 'Pick a chapter on the left to start reading',
  'reader.notFound': 'Book not found',
  'reader.loadingSource': 'Loading source text…',
  'reader.startAt': 'Showing from character {offset}',
  'reader.fromStart': 'Read from the start',
  'reader.progress': '{loaded} / {total} characters loaded',
  'reader.loading': 'Loading…',
  'reader.loadMore': 'Load more',

  'ask.title': 'Ask',
  'ask.description':
    'Describe your problem or dilemma, and it will look for an answer in the wisdom of the classics',
  'ask.modelButton': 'Model: {mode}',
  'ask.model.default': 'built-in',
  'ask.model.custom': 'custom',
  'ask.model.incomplete': 'not filled in',
  'ask.suggestionsTitle': 'Tell me what troubles you — for example:',
  'ask.suggestionsHint':
    'The knowledge base is classical Chinese text, so Chinese questions find the best matches. The answer still comes back in English.',
  'ask.cited': 'Cited {count} passages',
  'ask.aiAnswer': 'AI reading · {model}',
  'ask.localMode': 'Local retrieval only',
  'ask.saved': 'Saved to Echoes',
  'ask.thinking': 'Leafing through the classics…',
  'ask.placeholder': 'Type your question or dilemma…',
  'ask.inputLabel': 'Your question or dilemma',
  'ask.submit': 'Ask',
  'ask.composerHint': 'Enter to send · Shift + Enter for a new line',
  'ask.failed': 'Request failed, please try again later',

  'history.title': 'Echoes',
  'history.description':
    'Every question you asked and every answer you got, kept for the last fortnight only',
  'history.clear': 'Clear all',
  'history.total': '{count} in total',
  'history.retention': 'keeps the last {days} days',
  'history.nextPurge': 'next automatic cleanup {day}',
  'history.dbPath': 'Records are stored at {path}',
  'history.unavailable':
    'History is unavailable right now: {error}. Everything else — including Ask — still works; this question just will not be recorded.',
  'history.loading': 'Looking through earlier exchanges…',
  'history.empty': 'No records yet — go to Ask and pose a question',
  'history.cited': 'Cited {count} passages',
  'history.aiAnswer': 'AI reading · {model}',
  'history.localMode': 'Local retrieval only',
  'history.askAgain': 'Ask again',
  'history.delete': 'Delete',
  'history.loadMoreBusy': 'Loading…',
  'history.loadMore': 'Load more ({count} left)',
  'history.confirmClear': 'Clear all history? This cannot be undone.',
  'history.loadFailed': 'Could not read the history',
  'history.loadMoreFailed': 'Could not read more records',
  'history.deleteFailed': 'Delete failed',
  'history.clearFailed': 'Clear failed',
  'history.justNow': 'just now',
  'history.minutesAgo': '{count} min ago',
  'history.hoursAgo': '{count} h ago',
  'history.daysAgo': '{count} d ago',
  'history.noDate': '—',

  'insight.title': 'Insights',
  'insight.description': 'One piece of classical wisdom a day, as a small reminder for life',
  'insight.daily': 'Today’s insight',
  'insight.random': 'Another one',
  'insight.byTheme': 'Browse by theme',
  'insight.all': 'All',
  'insight.pickTheme': 'Pick a theme to see what the different classics have to say',
  'insight.emptyTheme': 'Nothing under this theme yet',

  'model.default': 'Built-in model',
  'model.custom': 'Custom model',
  'model.needFields': 'Fill in the base URL and API key first',
  'model.connected': 'Connected — now using {model}',
  'model.unreachable': 'Cannot reach this address',
  'model.requestFailed': 'Request failed, please try again later',
  'model.testing': 'Connecting…',
  'model.test': 'Test connection',
  'model.defaultHint':
    'Uses the model configured inside the app — nothing to set up. To use your own model (an in-house deployment, or another provider’s key), switch to “Custom model”.',
  'model.baseUrl': 'Base URL',
  'model.baseUrlHint': 'Root URL of an OpenAI-compatible API, including the trailing /v1.',
  'model.apiKey': 'API key',
  'model.apiKeyHint':
    'Kept only in this computer’s browser. It is never uploaded anywhere, and never written into the program files.',
  'model.modelName': 'Model name (optional)',
  'model.modelPlaceholder': 'Leave blank to pick automatically',
  'model.modelHint':
    'Left blank, the app picks one working model from that address and fails over if it breaks. Filled in, that one model is used exclusively — if it is unavailable the app falls back to local retrieval rather than silently switching to another model.',
  'model.okModels': ' ({count} models offered by this address)',
  'model.failModels': ' ({count} models offered, but none of them produced any text)',
  'model.incompleteHint':
    'Ask will only use this model once both the base URL and the API key are filled in; until then it keeps using the built-in model.',
}

export const MESSAGES: Record<Lang, Record<MessageKey, string>> = { zh: ZH, en: EN }

/* ── 术语表 ──────────────────────────────────────────────────────────
 *
 * 书名 / 作者 / 类目 / 主题来自后端，是语料的一部分。它们是**封闭集合**
 * （15 本书、7 个类目、8 个主题），所以翻译它们成本很低，而收益是英文界面下
 * 还能认出"这是哪本书"。查不到就原样返回——语料增补了新书时，
 * 界面会显示中文书名而不是变成空白或 `undefined`。
 */

const BOOK_TITLES: Record<string, string> = {
  易经: 'I Ching',
  厚黑学: 'Thick Black Theory',
  奇门遁甲: 'Qimen Dunjia',
  人性的弱点: 'How to Win Friends and Influence People',
  毛泽东选集: 'Selected Works of Mao Zedong',
  王阳明心学: 'Wang Yangming’s School of Mind',
  孙子兵法: 'The Art of War',
  道德经: 'Tao Te Ching',
  论语: 'The Analects',
  菜根谭: 'Caigentan',
  鬼谷子: 'Guiguzi',
  战国策: 'Strategies of the Warring States',
  史记: 'Records of the Grand Historian',
  资治通鉴: 'Zizhi Tongjian',
  贞观政要: 'Zhenguan Governmental Principles',
}

const AUTHORS: Record<string, string> = {
  '周文王/周公（传）': 'King Wen & the Duke of Zhou (attrib.)',
  李宗吾: 'Li Zongwu',
  佚名: 'Anonymous',
  '戴尔·卡耐基': 'Dale Carnegie',
  毛泽东: 'Mao Zedong',
  王守仁: 'Wang Shouren (Wang Yangming)',
  孙武: 'Sun Wu (Sun Tzu)',
  老子: 'Laozi',
  孔子弟子辑录: 'Compiled by Confucius’ disciples',
  洪应明: 'Hong Yingming',
  鬼谷子: 'Guiguzi',
  '刘向 编订': 'Edited by Liu Xiang',
  司马迁: 'Sima Qian',
  司马光: 'Sima Guang',
  吴兢: 'Wu Jing',
}

const CATEGORIES: Record<string, string> = {
  哲学: 'Philosophy',
  处世: 'Conduct',
  术数: 'Divination',
  政治: 'Politics',
  兵学: 'Military',
  纵横: 'Diplomacy',
  历史文献: 'History',
}

const THEMES: Record<string, string> = {
  逆境: 'Adversity',
  进退: 'Choice',
  修心: 'Self-cultivation',
  立志: 'Aspiration',
  处世: 'Getting along',
  谋略: 'Strategy',
  谦逊: 'Humility',
  恒心: 'Perseverance',
}

function lookup(map: Record<string, string>, value: string, lang: Lang): string {
  if (lang === 'zh' || !value) return value
  return map[value] ?? value
}

export const bookTitle = (value: string, lang: Lang) => lookup(BOOK_TITLES, value, lang)
export const authorName = (value: string, lang: Lang) => lookup(AUTHORS, value, lang)
export const categoryName = (value: string, lang: Lang) => lookup(CATEGORIES, value, lang)
export const themeName = (value: string, lang: Lang) => lookup(THEMES, value, lang)

/** 检索结果/金句的出处标注，形如 `《资治通鉴》· 才与德`。
 *
 * 英文界面下把书名换掉，章句名保留——它本身就是语料里的中文标题，
 * 硬翻反而会让人对不上原文。 */
export function sourceLabel(value: string, lang: Lang): string {
  if (lang === 'zh' || !value) return value
  return value.replace(/《([^》]+)》/g, (whole, name: string) => BOOK_TITLES[name] ?? whole)
}

/** `{name}` 占位替换。没有参数时原样返回，省去每个调用点的判断。 */
export function fill(template: string, params?: Record<string, string | number>): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole,
  )
}

/** 非 React 环境下取文案（`api/client.ts` 抛错、纯函数格式化）。
 *
 * React 组件一律用 `useI18n()`，那里语言变化会触发重渲染；
 * 这个函数读的是"当前生效语言"，靠 Provider 同步。 */
let active: Lang = DEFAULT_LANG

export function setActiveLang(lang: Lang): void {
  active = lang
}

export function activeLang(): Lang {
  return active
}

export function tCurrent(key: MessageKey, params?: Record<string, string | number>): string {
  return fill(MESSAGES[active][key], params)
}

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
  'nav.knowledge': '知识库',
  'nav.ask': '求教',
  'nav.history': '回响',
  'nav.profile': '画像',
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
  'history.description': '问过的困惑与得到的回答都收在这里，同一件事的追问归在一处，只留最近半个月',
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
  'history.loadMore': '加载更多（还有 {count} 个话题）',
  'history.topicTurns': '{count} 轮追问',
  'history.expand': '展开这段对话',
  'history.collapse': '收起',
  'history.loadingTopic': '正在展开这段对话…',
  'history.deleteTopic': '删除整段',
  'history.confirmDeleteTopic': '确定删除这整段对话（共 {count} 轮）吗？此操作不可撤销。',
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

  // ── 画像 ────────────────────────────────────────────────────
  'profile.title': '画像',
  'profile.description':
    '它只从你自己问过的话里，慢慢拼出"你是谁"——没有依据的一律不写，也从不替你猜',
  'profile.loading': '正在读取画像…',
  'profile.empty': '还没有归纳出任何特征。先去「求教」问几个问题，再回来这里。',
  'profile.emptyHint': '描述得越具体，它越认得出你。',
  'profile.total': '共 {count} 条特征',
  'profile.avatarGroup': '形象',
  'profile.avatar.male': '男',
  'profile.avatar.female': '女',
  'profile.figureAlt': '你的形象',
  'profile.figureCredit.male': '陈洪绶《仿古图册·陶渊明像》',
  'profile.figureCredit.female': '陈洪绶《仿古图册·仕女》',
  'profile.figureSource': '克利夫兰艺术博物馆藏',
  // —— 最像你的一位历史人物 ——
  // 还没评出人来时，中间那一栏就是上面的册页；评出来了就换成那个人。
  'profile.figure.picked': '最像你的一位',
  'profile.figure.reason': '像在哪里',
  'profile.figure.meta': '{date} 从 {count} 位候选人中选出',
  'profile.figure.evaluate': '重新评定',
  'profile.figure.evaluating': '正在评定…',
  'profile.figure.done': '评定了最像你的一位',
  'profile.figure.none': '这一册名录里还没有人。',
  'profile.extract': '重新归纳',
  'profile.extracting': '正在归纳…',
  'profile.pending': '有 {count} 条新提问还没归纳过',
  'profile.autoExtracting': '已经问过 {count} 条，正在归纳…',
  'profile.extracted': '新增 {count} 条特征',
  'profile.nothingNew': '这次没读出新的东西',
  'profile.clear': '清空画像',
  'profile.confirmClear': '确定清空画像吗？问答记录不会受影响，之后可以重新归纳。',
  'profile.deleteTrait': '删掉这条',
  'profile.evidence': '依据：{text}',
  'profile.confidence': '把握 {percent}%',
  'profile.unavailable': '画像暂时用不了：{error}。问答记录与其它功能不受影响。',
  'profile.loadFailed': '读取画像失败',
  'profile.extractFailed': '归纳失败，请稍后再试',
  'profile.figureFailed': '评定失败，请稍后再试',
  'profile.deleteFailed': '删除失败',
  'profile.err.noRecords': '还没有求教记录——先去「求教」问几个问题，再回来归纳',
  'profile.err.noLlm': '当前没有可用的模型，归纳暂时做不了',
  'profile.err.noLlmFigure': '当前没有可用的模型，评定暂时做不了',
  'profile.err.nothingNew': '这次没读出新的特征。多聊几次，线索够了再来。',
  'profile.err.noTraits': '还没有可依的画像——先归纳一次，再来评定',
  'profile.err.noPool': '这一册名录里还没有候选人，评定无从做起',
  'profile.err.notInPool': '模型给的名字不在名录里，这次不算数',
  'profile.err.noStore': '画像暂时用不了，无法评定',
  'profile.footnote': '特征由模型归纳，可能出错。看着不认同的那条，删掉就好。',

  // ── 感悟 ────────────────────────────────────────────────────
  'insight.title': '感悟',
  'insight.description': '每日一句经典智慧，给生活一点提醒',
  'insight.daily': '今日感悟',
  'insight.random': '随机一则',
  'insight.byTheme': '按主题浏览',
  'insight.all': '全部',
  'insight.pickTheme': '选择一个主题，看看不同的经典怎么说',
  'insight.emptyTheme': '该主题下暂无感悟',

  // ── 知识库 ─────────────────────────────────────────────────
  'kb.title': '知识库',
  'kb.description': '{books} 部经典 · {themes} 个主题 · {edges} 条关联',
  'kb.scopeGroup': '图上显示',
  'kb.scope.all': '全部',
  'kb.scope.book': '只看书',
  'kb.scope.theme': '只看主题',
  'kb.chapters': '展开章节',
  'kb.chaptersHint': '把全部章节一并铺在图上——看得见每一章，但书与书之间的结构会被淹没',
  'kb.searchLabel': '查找节点',
  'kb.searchPlaceholder': '输入书名或主题，例如：道德经',
  'kb.searchSubmit': '查找',
  'kb.searchEmpty': '没有匹配的节点',
  'kb.focused': '正在看：{name}',
  'kb.backToFull': '返回全图',
  'kb.legend.book': '经典',
  'kb.legend.theme': '主题',
  'kb.legend.chapter': '章节',
  'kb.legend.cross': '经典互参',
  'kb.legend.hint': '点一个节点看它的双链；再点一次回到全图',
  'kb.canvasLabel': '经典之间的关系图谱',
  'kb.empty': '知识库还是空的',
  'kb.loadFailed': '读不到知识库',
  'kb.link.outgoing': '出链 · 它引用了',
  'kb.link.backlinks': '反向链接 · 谁引用了它',
  'kb.link.noneOutgoing': '这本书没有写明与哪部经典相通',
  'kb.link.noneBacklinks': '还没有别的书写到它',
  'kb.kind.theme': '主题归属',
  'kb.kind.cross': '经典互参',
  'kb.kind.part': '章节构成',
  'kb.themeRows': '在八个主题下',
  'kb.crossRefs': '写下的互参',
  'kb.judgmentOf': '{book}的判断',
  'kb.read': '去阅读',
  'kb.openChapter': '打开这一章',
  'kb.meta.author': '作者',
  'kb.meta.category': '类目',
  'kb.meta.chapters': '章数',
  'kb.meta.source': '原典',
  'kb.meta.hasSource': '含原典全文',
  'kb.meta.noSource': '暂无原典',
  'kb.meta.degree': '关联 {count} 条',
  'kb.pickHint': '点图上的节点，看它引用了什么、又被谁引用。',
  'kb.scopeUnavailable': '这个筛选下没有节点',

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
  'nav.knowledge': 'Knowledge',
  'nav.ask': 'Ask',
  'nav.history': 'Echoes',
  'nav.profile': 'Portrait',
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
    'Every question and answer, follow-ups kept together with the question they belong to — last fortnight only',
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
  'history.loadMore': 'Load more ({count} conversations left)',
  'history.topicTurns': '{count} turns',
  'history.expand': 'Show the conversation',
  'history.collapse': 'Collapse',
  'history.loadingTopic': 'Opening the conversation…',
  'history.deleteTopic': 'Delete the whole conversation',
  'history.confirmDeleteTopic':
    'Delete this whole conversation ({count} turns)? This cannot be undone.',
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

  'profile.title': 'Portrait',
  'profile.description':
    'Built only from the questions you have asked — nothing without evidence, and it never guesses on your behalf',
  'profile.loading': 'Reading your portrait…',
  'profile.empty':
    'Nothing recorded yet. Go to Ask and pose a few questions, then come back here.',
  'profile.emptyHint': 'The more specifically you describe things, the better it knows you.',
  'profile.total': '{count} traits in all',
  'profile.avatarGroup': 'Figure',
  'profile.avatar.male': 'Male',
  'profile.avatar.female': 'Female',
  'profile.figureAlt': 'Your figure',
  'profile.figureCredit.male': 'Chen Hongshou, “Portrait of Tao Yuanming”',
  'profile.figureCredit.female': 'Chen Hongshou, “A Lady”',
  'profile.figureSource': 'Cleveland Museum of Art',
  // —— the historical figure you most resemble ——
  'profile.figure.picked': 'The one you most resemble',
  'profile.figure.reason': 'Where the likeness lies',
  'profile.figure.meta': 'Chosen {date}, from {count} candidates',
  'profile.figure.evaluate': 'Judge it again',
  'profile.figure.evaluating': 'Judging…',
  'profile.figure.done': 'Chosen the one you most resemble',
  'profile.figure.none': 'There is nobody in this album yet.',
  'profile.extract': 'Read them again',
  'profile.extracting': 'Reading…',
  'profile.pending': '{count} new questions not read yet',
  'profile.autoExtracting': '{count} questions so far — reading them now…',
  'profile.extracted': 'Added {count} traits',
  'profile.nothingNew': 'Nothing new came out of it this time',
  'profile.clear': 'Clear the portrait',
  'profile.confirmClear':
    'Clear the portrait? Your question history is untouched and you can read it again later.',
  'profile.deleteTrait': 'Remove',
  'profile.evidence': 'Because: {text}',
  'profile.confidence': '{percent}% sure',
  'profile.unavailable':
    'The portrait is unavailable right now: {error}. Your history and everything else still work.',
  'profile.loadFailed': 'Could not read the portrait',
  'profile.extractFailed': 'Could not read it — please try again later',
  'profile.figureFailed': 'Could not judge it — please try again later',
  'profile.deleteFailed': 'Delete failed',
  'profile.err.noRecords': 'No questions yet — ask a few in Ask, then come back',
  'profile.err.noLlm': 'No model is available right now, so this cannot be read',
  'profile.err.noLlmFigure': 'No model is available right now, so this cannot be judged',
  'profile.err.nothingNew':
    'Nothing new this time. Talk a while longer, then come back once there is more to go on.',
  'profile.err.noTraits': 'Nothing to go on yet — read your traits first',
  'profile.err.noPool': 'There is nobody in this album to choose from',
  'profile.err.notInPool':
    'The model named someone outside the album, so it does not count',
  'profile.err.noStore': 'The portrait is unavailable, so nobody can be chosen',
  'profile.footnote':
    'Traits are inferred by a model and can be wrong. If one does not ring true, just remove it.',

  'insight.title': 'Insights',
  'insight.description': 'One piece of classical wisdom a day, as a small reminder for life',
  'insight.daily': 'Today’s insight',
  'insight.random': 'Another one',
  'insight.byTheme': 'Browse by theme',
  'insight.all': 'All',
  'insight.pickTheme': 'Pick a theme to see what the different classics have to say',
  'insight.emptyTheme': 'Nothing under this theme yet',

  // ── Knowledge base ─────────────────────────────────────────
  'kb.title': 'Knowledge base',
  'kb.description': '{books} classics · {themes} themes · {edges} links',
  'kb.scopeGroup': 'Show on graph',
  'kb.scope.all': 'All',
  'kb.scope.book': 'Books only',
  'kb.scope.theme': 'Themes only',
  'kb.chapters': 'Show chapters',
  'kb.chaptersHint':
    'Lays every chapter onto the graph — you can see each one, but the structure between books drowns',
  'kb.searchLabel': 'Find a node',
  'kb.searchPlaceholder': 'Book or theme, e.g. 道德经',
  'kb.searchSubmit': 'Find',
  'kb.searchEmpty': 'No matching node',
  'kb.focused': 'Viewing: {name}',
  'kb.backToFull': 'Back to the whole graph',
  'kb.legend.book': 'Classic',
  'kb.legend.theme': 'Theme',
  'kb.legend.chapter': 'Chapter',
  'kb.legend.cross': 'Cross-reference',
  'kb.legend.hint': 'Click a node to see its links; click it again to go back',
  'kb.canvasLabel': 'Graph of the relationships between the classics',
  'kb.empty': 'The knowledge base is empty',
  'kb.loadFailed': 'Could not read the knowledge base',
  'kb.link.outgoing': 'Outgoing · it refers to',
  'kb.link.backlinks': 'Backlinks · referred to by',
  'kb.link.noneOutgoing': 'This book names no other classic',
  'kb.link.noneBacklinks': 'No other book mentions it yet',
  'kb.kind.theme': 'Theme',
  'kb.kind.cross': 'Cross-reference',
  'kb.kind.part': 'Chapter',
  'kb.themeRows': 'Across the eight themes',
  'kb.crossRefs': 'Cross-references written',
  'kb.judgmentOf': 'On {book}',
  'kb.read': 'Read',
  'kb.openChapter': 'Open this chapter',
  'kb.meta.author': 'Author',
  'kb.meta.category': 'Category',
  'kb.meta.chapters': 'Chapters',
  'kb.meta.source': 'Source text',
  'kb.meta.hasSource': 'Full source included',
  'kb.meta.noSource': 'No source text yet',
  'kb.meta.degree': '{count} links',
  'kb.pickHint':
    'Click a node to see what it refers to, and who refers to it.',
  'kb.scopeUnavailable': 'No node under this filter',

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

/** 画像的七个分类。与后端 `profile.TRAIT_CATEGORIES` 一一对应——
 *  那边是封闭集合（不在里面的特征会被丢掉），所以这里也不会有查不到的情况；
 *  真查不到就原样显示中文，不至于变成空白。 */
const TRAIT_CATEGORIES: Record<string, string> = {
  性格: 'Character',
  年龄: 'Age',
  爱好: 'Interests',
  生活条件: 'Living situation',
  成熟度: 'Maturity',
  专业: 'Profession',
  规划: 'Plans',
}

function lookup(map: Record<string, string>, value: string, lang: Lang): string {
  if (lang === 'zh' || !value) return value
  return map[value] ?? value
}

export const bookTitle = (value: string, lang: Lang) => lookup(BOOK_TITLES, value, lang)
export const authorName = (value: string, lang: Lang) => lookup(AUTHORS, value, lang)
export const categoryName = (value: string, lang: Lang) => lookup(CATEGORIES, value, lang)
export const themeName = (value: string, lang: Lang) => lookup(THEMES, value, lang)
export const traitCategory = (value: string, lang: Lang) =>
  lookup(TRAIT_CATEGORIES, value, lang)

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

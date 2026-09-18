import { lazy, Suspense } from 'react'
import { Route, Routes, NavLink } from 'react-router-dom'
import LangToggle from './components/LangToggle'
import { Loading } from './components/Status'
import { useI18n, type MessageKey } from './i18n'

// 页面按路由**分包**：进哪一页才下载哪一页的代码。
//
// 原先八个页面全是静态 import，会被打进同一个 chunk——打开「书架」也得先把
// 画像、知识图谱、阅读器的代码一起下载并解析完，才看得到第一屏。桌面版虽然
// 是本地加载，省下的这点网络时间不算什么，但**解析与执行**同样要花，且每个
// 页面都在为别的页面付这份钱。
//
// 代价是切到没去过的页面时多一次本地取 chunk（几毫秒）。Suspense 的兜底
// 用同一个 Loading 组件，所以万一真的慢，看到的也是熟悉的样子，不会白屏。
const Library = lazy(() => import('./pages/Library'))
const Reader = lazy(() => import('./pages/Reader'))
const Advisor = lazy(() => import('./pages/Advisor'))
const History = lazy(() => import('./pages/History'))
const Knowledge = lazy(() => import('./pages/Knowledge'))
const Profile = lazy(() => import('./pages/Profile'))
const Insights = lazy(() => import('./pages/Insights'))
const Search = lazy(() => import('./pages/Search'))

const NAV_ITEMS: { to: string; key: MessageKey; end?: boolean }[] = [
  { to: '/', key: 'nav.library', end: true },
  { to: '/search', key: 'nav.search' },
  { to: '/ask', key: 'nav.ask' },
  // 「回响」紧跟「求教」：它存的就是求教留下的记录，两块内容是一体的
  { to: '/history', key: 'nav.history' },
  // 「画像」接着「回响」：它归纳的也正是那些记录，是同一批素材的另一种看法
  { to: '/profile', key: 'nav.profile' },
  { to: '/insights', key: 'nav.insights' },
]

export default function App() {
  const { t } = useI18n()

  return (
    <div className="flex min-h-screen flex-col bg-paper-100">
      <header className="sticky top-0 z-20 border-b border-paper-200 bg-paper-100/90 backdrop-blur-md">
        {/* 允许换行：窄屏下"品牌 + 五个导航项 + 语言开关"必然放不下一行，
            宁可在顶栏内折成两行，也不要把导航项挤成半个字 */}
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
          <NavLink to="/" className="flex items-baseline gap-2">
            {/* 产品名保持中文原样：它是这方"书卷"的题字，
                不随界面语言变——就像不会把"微信"在英文界面上写成 WeChat */}
            <span className="font-serif text-xl font-bold tracking-tight text-ink-900">
              人生导师
            </span>
            <span className="hidden text-sm text-ink-400 sm:inline">{t('app.subtitle')}</span>
          </NavLink>

          <div className="flex items-center gap-2">
            <nav className="flex flex-wrap items-center gap-0.5" aria-label={t('nav.label')}>
              {NAV_ITEMS.map(item => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors sm:px-3 ${
                      isActive
                        ? 'bg-cinnabar-500 text-paper-50 shadow-card'
                        : 'text-ink-600 hover:bg-paper-200 hover:text-ink-900'
                    }`
                  }
                >
                  {t(item.key)}
                </NavLink>
              ))}
            </nav>
            <span aria-hidden="true" className="h-5 w-px bg-paper-300" />
            <LangToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<Library />} />
            <Route path="/books/:bookId" element={<Reader />} />
            <Route path="/search" element={<Search />} />
            <Route path="/knowledge" element={<Knowledge />} />
            <Route path="/ask" element={<Advisor />} />
            <Route path="/history" element={<History />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/insights" element={<Insights />} />
          </Routes>
        </Suspense>
      </main>

      <footer className="border-t border-paper-200 py-8 text-center">
        <p className="font-serif text-sm text-ink-400">{t('app.footer')}</p>
      </footer>
    </div>
  )
}

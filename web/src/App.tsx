import { Route, Routes, NavLink } from 'react-router-dom'
import Library from './pages/Library'
import Reader from './pages/Reader'
import Advisor from './pages/Advisor'
import History from './pages/History'
import Insights from './pages/Insights'
import Search from './pages/Search'
import LangToggle from './components/LangToggle'
import { useI18n, type MessageKey } from './i18n'

const NAV_ITEMS: { to: string; key: MessageKey; end?: boolean }[] = [
  { to: '/', key: 'nav.library', end: true },
  { to: '/search', key: 'nav.search' },
  { to: '/ask', key: 'nav.ask' },
  // 「回响」紧跟「求教」：它存的就是求教留下的记录，两块内容是一体的
  { to: '/history', key: 'nav.history' },
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
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/books/:bookId" element={<Reader />} />
          <Route path="/search" element={<Search />} />
          <Route path="/ask" element={<Advisor />} />
          <Route path="/history" element={<History />} />
          <Route path="/insights" element={<Insights />} />
        </Routes>
      </main>

      <footer className="border-t border-paper-200 py-8 text-center">
        <p className="font-serif text-sm text-ink-400">{t('app.footer')}</p>
      </footer>
    </div>
  )
}

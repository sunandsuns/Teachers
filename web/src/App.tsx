import { Route, Routes, NavLink } from 'react-router-dom'
import Library from './pages/Library'
import Reader from './pages/Reader'
import Advisor from './pages/Advisor'
import Insights from './pages/Insights'
import Search from './pages/Search'

const NAV_ITEMS = [
  { to: '/', label: '书架', end: true },
  { to: '/search', label: '寻章' },
  { to: '/ask', label: '求教' },
  { to: '/insights', label: '感悟' },
]

export default function App() {
  return (
    <div className="flex min-h-screen flex-col bg-paper-100">
      <header className="sticky top-0 z-20 border-b border-paper-200 bg-paper-100/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <NavLink to="/" className="flex items-baseline gap-2">
            <span className="font-serif text-xl font-bold tracking-tight text-ink-900">
              人生导师
            </span>
            {/* 副标题在窄屏隐藏，否则四个导航项会被挤到换行 */}
            <span className="hidden text-sm text-ink-400 sm:inline">经典智慧知识库</span>
          </NavLink>
          <nav className="flex shrink-0 items-center gap-0.5" aria-label="主导航">
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
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/books/:bookId" element={<Reader />} />
          <Route path="/search" element={<Search />} />
          <Route path="/ask" element={<Advisor />} />
          <Route path="/insights" element={<Insights />} />
        </Routes>
      </main>

      <footer className="border-t border-paper-200 py-8 text-center">
        <p className="font-serif text-sm text-ink-400">人生导师 · 中国传统经典智慧知识库</p>
      </footer>
    </div>
  )
}

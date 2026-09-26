import { useI18n } from '../../i18n'
import ContentStage from './ContentStage'
import TopBar from './TopBar'

/**
 * 正式界面的外壳：顶栏 + 内容区 + 页脚。
 *
 * 存在的意义是**把"页面之外的东西"从路由文件里挪走**。原来的 `App.tsx`
 * 一个文件里塞了懒加载声明、导航数据、顶栏 JSX、路由表、页脚五件事，
 * 改导航要翻到文件中间去动一段 JSX。现在 `App.tsx` 只剩一张路由表，
 * 布局归这里，导航归 `nav.ts`。
 *
 * 是一条**布局路由**（`element={<AppShell />}`），所以正文走 `<Outlet />`
 * ——转场与分包兜底这两件事封在 `ContentStage` 里，与账号页共用。
 *
 * 内容区宽度仍收在 `max-w-5xl`：这是个中文长文阅读为主的产品，
 * 再宽一行字数就超过舒适区（中文约 35~45 字/行）。
 */
export default function AppShell() {
  const { t } = useI18n()

  return (
    <div className="flex min-h-screen flex-col">
      {/* 跳转到正文。七个导航入口排在顶栏里，键盘用户每换一页都要 Tab 穿过去，
          这一个是"别再按了，直接跳到内容"的出口。平时视觉隐藏（sr-only），
          聚焦时才现身——它不该在视觉上参与版面。 */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-cinnabar-500 focus:px-4 focus:py-2 focus:text-sm focus:text-paper-50 focus:shadow-lift"
      >
        {t('app.skipToContent')}
      </a>
      <TopBar />
      <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
        <ContentStage />
      </main>
      <footer className="mt-4 border-t border-paper-200/70 py-8 text-center">
        <p className="font-serif text-sm text-ink-400">{t('app.footer')}</p>
      </footer>
    </div>
  )
}

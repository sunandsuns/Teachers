import { useI18n } from '../../i18n'
import LangToggle from '../LangToggle'
import ContentStage from './ContentStage'

/**
 * 账号页的整屏外壳：登录页与注册页的家。
 *
 * 为什么不让它们套 `AppShell`
 * --------------------------------------------------------------------------
 * 这套产品的入口现在就是登录页——**登录之前一个页面也看不了**。那么顶栏
 * 上那排导航（书架 / 寻章 / 知识库 / 求教 / 回响 / 画像 / 感悟 / 后台）在
 * 未登录的人眼里是七个同样的死胡同：点哪个都会回到这一页。把导航拿掉，
 * 留下的就只有"这是什么产品"与"怎么进去"两件事。
 *
 * 所以这里与 `AppShell` 的分工是**内容之外的一切**：品牌（产品名与副题）、
 * 语言切换、页脚。真正的表单由 `features/auth/AuthPage` 提供，舞台与分包
 * 兜底两边共用 `ContentStage`。
 *
 * 品牌不做成链接：此刻点它只会被弹回这一页，那比不能点更让人困惑。
 */
export default function AuthLayout() {
  const { t } = useI18n()

  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex justify-end px-4 py-3 sm:px-6">
        <LangToggle />
      </div>

      <main id="main" className="flex flex-1 flex-col items-center justify-center px-4 pb-12">
        <div className="mb-8 text-center">
          {/* 产品名保持中文原样，与顶栏一致：它是这方"书卷"的题字，
              不随界面语言变——就像不会把"微信"在英文界面上写成 WeChat */}
          <p className="font-serif text-3xl font-bold tracking-tight text-ink-900">人生导师</p>
          <p className="mt-2 text-sm text-ink-400">{t('app.subtitle')}</p>
        </div>

        <div className="w-full max-w-sm">
          <ContentStage />
        </div>
      </main>

      <footer className="py-8 text-center">
        <p className="font-serif text-sm text-ink-400">{t('app.footer')}</p>
      </footer>
    </div>
  )
}

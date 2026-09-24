/** @type {import('tailwindcss').Config} */

// ── 设计令牌（Design Tokens）──────────────────────────────────────────
//
// 这一层是整个界面的**唯一真源**。任何页面都不该再写死颜色、时长、阴影、
// 圆角——需要新的，就回这里加一个令牌，而不是在某个 className 里塞
// `duration-[420ms]` 或 `shadow-[0_2px_8px_rgba(...)]`。
//
// 分四组：
//   1. colors      色（宣纸 / 墨 / 朱砂 / 青瓷）
//   2. motion      动（时长 + 缓动）——"流畅"这件事的根子在这里，不在组件里
//   3. elevation   影（抬升阶梯）
//   4. typography  字（无衬线 / 衬线 / 楷体）
//
// 运动曲线的取法参考了几家国外大厂的做法：
//   · expo-out `cubic-bezier(0.16, 1, 0.3, 1)` —— Linear / Vercel 系的招牌曲线。
//     起手极快、收尾极缓，落定时有"被吸住"的手感，而不是匀速滑到位。
//   · 回弹 `cubic-bezier(0.34, 1.56, 0.64, 1)` —— 轻微过冲，只给"按下去又弹起"
//     这类小元件用。大块内容回弹会晕，所以不做成默认。

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 宣纸 —— 页面与卡片的暖白层次。page 用 100，surface 用 50，形成"纸叠纸"的层次。
        paper: {
          50: '#fbfaf6',
          100: '#f6f3ea',
          200: '#ece6d7',
          300: '#ddd4bd',
          400: '#c9bc9d',
          500: '#b3a37f',
        },
        // 墨 —— 正文与界面的深浅层级
        ink: {
          50: '#f4f3f1',
          100: '#e6e4e0',
          200: '#cfccc6',
          300: '#b0aca3',
          400: '#8a857a',
          500: '#6b665c',
          600: '#555047',
          700: '#44403a',
          800: '#2f2c27',
          900: '#1e1c19',
        },
        // 朱砂 —— 主强调色。补全色阶后，hover / 描边 / 浅底都有正式令牌，不再靠透明度硬凑。
        cinnabar: {
          50: '#fdf4f2',
          100: '#fbe5e1',
          200: '#f6cbc4',
          300: '#eda69b',
          400: '#dd7767',
          500: '#c0392b',
          600: '#a32e22',
          700: '#86261c',
        },
        // 青瓷 —— 次强调色（历史文献、成功态）
        celadon: {
          50: '#f2f6f4',
          100: '#e3ece8',
          200: '#c6d9d1',
          300: '#a0c0b3',
          400: '#6f9c8b',
          500: '#4a6b5d',
          600: '#3b564a',
          700: '#2f453b',
        },
      },

      fontFamily: {
        // 界面用无衬线：导航、按钮、标签、表格这类小字，宋体在屏幕上笔画过细、可读性差
        sans: [
          '"PingFang SC"',
          '"Microsoft YaHei"',
          '"Hiragino Sans GB"',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'sans-serif',
        ],
        // 内容用衬线：书目正文、Markdown、引文
        serif: [
          '"Noto Serif SC"',
          '"Source Han Serif SC"',
          '"Songti SC"',
          'STSong',
          'SimSun',
          'Georgia',
          'serif',
        ],
        // 楷体：只用于大字号的经典引文，正文不用（小字号可读性差）
        kai: ['KaiTi', 'STKaiti', '"Kaiti SC"', '"Noto Serif SC"', 'serif'],
      },

      // ── 动（motion）────────────────────────────────────────────
      // 时长分四档，语义化命名而不是数字。组件里写 duration-snap 比写
      // duration-100 更能说明"这一下要多快"。
      transitionDuration: {
        snap: '120ms', // 按下 / 抬起这种即时反馈
        quick: '200ms', // 颜色、描边这类便宜的变化
        calm: '320ms', // 位移、尺寸这类需要看清过程的变化
        slow: '520ms', // 入场 / 退场
      },
      transitionTimingFunction: {
        // 默认缓动：进出对称，适合 hover 这种会来回的变化
        swift: 'cubic-bezier(0.4, 0, 0.2, 1)',
        // 招牌曲线：起手快、收尾极缓。入场与"移动到新位置"都用它
        spring: 'cubic-bezier(0.16, 1, 0.3, 1)',
        // 轻微过冲：只给小元件（药丸、开关）用
        bounce: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },

      // ── 影（elevation）─────────────────────────────────────────
      // 抬升阶梯。名字表达"离纸面多高"，而不是"多黑"。
      boxShadow: {
        // 静置：几乎只是描边的补充
        card: '0 1px 2px rgba(30, 28, 25, 0.04), 0 1px 3px rgba(30, 28, 25, 0.06)',
        // 悬停：离纸面抬起一档
        lift: '0 10px 28px -10px rgba(30, 28, 25, 0.18), 0 2px 6px rgba(30, 28, 25, 0.06)',
        // 浮起：菜单、抽屉、被拖动的元素
        float: '0 18px 44px -14px rgba(30, 28, 25, 0.26), 0 4px 10px -4px rgba(30, 28, 25, 0.10)',
        // 底部输入栏专用的向上投影
        composer: '0 -4px 20px -6px rgba(30, 28, 25, 0.12)',
        // 画心贴在纸上的那点厚度。比 card 深一档，但仍是"纸"而不是"卡片"。
        leaf: '0 1px 2px rgba(30, 28, 25, 0.10), 0 5px 14px -6px rgba(30, 28, 25, 0.22)',
        // 焦点态的光晕。用朱砂而不是中性色，和焦点环同源
        glow: '0 0 0 4px rgba(221, 119, 103, 0.18)',
        // 内凹：输入框这类"要往纸里按"的表面
        'inset-soft': 'inset 0 1px 2px rgba(30, 28, 25, 0.06)',
      },

      // 顶栏高约 3.25rem + 上下留白，两者共用一个基准值，
      // 免得以后再写 max-h-[70vh] / style={{minHeight:'calc(100vh-13rem)'}} 这类散落的魔法数
      maxHeight: {
        sidebar: 'calc(100vh - 13rem)',
      },
      minHeight: {
        panel: 'calc(100vh - 13rem)',
      },

      // 「画像」的形象是两页册页（陈洪绶《仿古图册》），外面套一个 9:10 的画框。
      // 画心本身按各自的比例裁好（`web/src/assets/figure-*.webp`），比例差额
      // 靠 `object-contain` + `paper-200` 底色补——所以改这里的值只是改"镜框"，
      // 不会把画压扁，但会改变留白多少。
      aspectRatio: {
        portrait: '9 / 10',
      },

      // ── 入场关键帧 ─────────────────────────────────────────────
      // 只保留"出现"这一种意图的几个变体。位移方向固定（自下而上），
      // 因为中文阅读是从上往下，内容自下浮起最符合"翻到这一页"的直觉。
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'none' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        // 内容块入场：比 fade-up 走得更远、带一点点缩放，
        // 用 expo-out 收尾，落定时有"停稳"而不是"撞停"的感觉
        rise: {
          '0%': { opacity: '0', transform: 'translateY(16px) scale(0.985)' },
          '100%': { opacity: '1', transform: 'none' },
        },
        // 小元件（卡片、药丸）入场
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'none' },
        },
        // 自上方落下：展开面板、下拉内容
        'drop-in': {
          '0%': { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '1', transform: 'none' },
        },
        // 呼吸：等待态用。比 animate-pulse 更轻，不抢视线
        breathe: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.45' },
        },

        // ── 换模块的转场 ───────────────────────────────────────────
        // 三个方向，对应三种"移动"：
        //   forward  往导航右边走 → 新页面从右侧进来
        //   back     往导航左边走 → 新页面从左侧进来
        //   depth    不在导航上的移动（进一本书、去登录）→ 自下浮起
        //
        // 位移只给 34px、旋转只给 1.8deg。整屏横移会让人以为在翻相册，
        // 而这里要表达的是"内容换了一版"，不是"翻了一页"——所以只给一点点，
        // 够让眼睛读出方向就行。
        //
        // 旋转写在 transform 里的 `perspective()`，**不是**给父元素加
        // `perspective` 属性：后者会让祖先永久成为绝对/固定定位的包含块，
        // 也会多出一个层叠上下文，牵连页面里所有定位元素。写成变换函数就
        // 只作用于这一层，而且末帧是 `transform: none`，动画结束后不留痕迹。
        'stage-forward': {
          '0%': {
            opacity: '0',
            transform: 'perspective(1200px) translate3d(34px, 0, 0) rotateY(1.8deg)',
          },
          '100%': { opacity: '1', transform: 'none' },
        },
        'stage-back': {
          '0%': {
            opacity: '0',
            transform: 'perspective(1200px) translate3d(-34px, 0, 0) rotateY(-1.8deg)',
          },
          '100%': { opacity: '1', transform: 'none' },
        },
        // 纵深：自下浮起 + 顶端微微后仰，像一张牌落定。
        // 只有这一向带缩放——横向的两向再加缩放就成了"又滑又推"，
        // 元素一多会显得忙；而且缩放会让文字在动画期间落在非整数像素上。
        'stage-depth': {
          '0%': {
            opacity: '0',
            transform: 'perspective(1200px) translate3d(0, 20px, 0) scale(0.99) rotateX(1.4deg)',
          },
          '100%': { opacity: '1', transform: 'none' },
        },
      },
      animation: {
        'fade-up': 'fade-up 220ms cubic-bezier(0.16, 1, 0.3, 1) both',
        'fade-in': 'fade-in 200ms ease-out both',
        rise: 'rise 520ms cubic-bezier(0.16, 1, 0.3, 1) both',
        'scale-in': 'scale-in 320ms cubic-bezier(0.16, 1, 0.3, 1) both',
        'drop-in': 'drop-in 240ms cubic-bezier(0.16, 1, 0.3, 1) both',
        breathe: 'breathe 1.8s ease-in-out infinite',

        // 转场用 320ms（= duration-calm）与招牌缓动，**刻意和顶栏的滑动指示器
        // 对齐**：指示器也在 320ms 内滑到新位置，两边同起同落，整屏看起来是
        // 一个动作，而不是"页面在动、导航也在动"两件事。
        'stage-forward': 'stage-forward 320ms cubic-bezier(0.16, 1, 0.3, 1) both',
        'stage-back': 'stage-back 320ms cubic-bezier(0.16, 1, 0.3, 1) both',
        'stage-depth': 'stage-depth 320ms cubic-bezier(0.16, 1, 0.3, 1) both',
      },
    },
  },
  plugins: [],
}

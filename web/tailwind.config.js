/** @type {import('tailwindcss').Config} */
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
      boxShadow: {
        card: '0 1px 2px rgba(30, 28, 25, 0.04), 0 1px 3px rgba(30, 28, 25, 0.06)',
        lift: '0 10px 28px -10px rgba(30, 28, 25, 0.18), 0 2px 6px rgba(30, 28, 25, 0.06)',
        composer: '0 -4px 20px -6px rgba(30, 28, 25, 0.12)',
      },
      // 顶栏高约 3.25rem + 上下留白，两者共用一个基准值，
      // 免得以后再写 max-h-[70vh] / style={{minHeight:'calc(100vh-13rem)'}} 这类散落的魔法数
      maxHeight: {
        sidebar: 'calc(100vh - 13rem)',
      },
      minHeight: {
        panel: 'calc(100vh - 13rem)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'none' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        'fade-up': 'fade-up 220ms ease-out both',
        'fade-in': 'fade-in 200ms ease-out both',
      },
    },
  },
  plugins: [],
}

/** 语言上下文：语言从哪来、怎么存、组件怎么读。
 *
 * 只做界面语言，不碰语料。字典与术语表在 `messages.ts`。
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  DEFAULT_LANG,
  LANGS,
  MESSAGES,
  fill,
  setActiveLang,
  type Lang,
  type MessageKey,
} from './messages'

export type { Lang, MessageKey }
export {
  LANGS,
  DEFAULT_LANG,
  authorName,
  bookTitle,
  categoryName,
  sourceLabel,
  themeName,
  traitCategory,
} from './messages'

/** 与 `useModelSettings` 同理存在 localStorage：语言是本机偏好，
 * 为它往数据库或配置文件里写一笔不值当。 */
const STORAGE_KEY = 'rsds.lang'

export function readLang(): Lang {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return LANGS.includes(raw as Lang) ? (raw as Lang) : DEFAULT_LANG
  } catch {
    // 无痕模式或被禁用：本次会话仍可切换，只是记不住
    return DEFAULT_LANG
  }
}

// 让非 React 调用方（api/client.ts 的报错、纯函数格式化）从第一刻起就用对语言，
// 不必等 Provider 挂载。
setActiveLang(readLang())

export interface I18nValue {
  lang: Lang
  setLang: (lang: Lang) => void
  t: (key: MessageKey, params?: Record<string, string | number>) => string
}

/**
 * 没有 Provider 时的取值：恒为中文。
 *
 * 单测常常直接渲染某一页（不套 Provider），若这里给 undefined，
 * `useI18n()` 会把整页炸掉；而这些用例断言的本来就是中文原文，
 * 回落中文正好一致。
 */
const FALLBACK: I18nValue = {
  lang: DEFAULT_LANG,
  setLang: () => {},
  t: (key, params) => fill(MESSAGES[DEFAULT_LANG][key], params),
}

const Ctx = createContext<I18nValue>(FALLBACK)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readLang)

  useEffect(() => {
    setActiveLang(lang)
    // 读屏软件与浏览器的断词/引号规则都看这个属性，切了语言就得跟着改
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  }, [lang])

  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // 写不进去就只在本次会话内生效，不打扰用户
    }
  }, [])

  const value = useMemo<I18nValue>(
    () => ({
      lang,
      setLang,
      t: (key, params) => fill(MESSAGES[lang][key], params),
    }),
    [lang, setLang],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useI18n(): I18nValue {
  return useContext(Ctx)
}

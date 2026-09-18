import { LANGS, useI18n, type Lang } from '../i18n'
import Segmented from './ui/Segmented'

/** 界面语言切换。
 *
 * 每一项都用**它自己的语言**书写（中文 / EN）——切到英文后，
 * 中文用户也得能一眼找回中文，所以 `lang.zh` 在两种语言下都是"中文"。
 *
 * 放在顶栏而不是"设置"里：语言是随时想换的东西，
 * 尤其是误切之后，让人去设置页里找回来太远了。
 */
export default function LangToggle() {
  const { lang, setLang, t } = useI18n()

  return (
    <Segmented<Lang>
      value={lang}
      ariaLabel={t('lang.group')}
      options={LANGS.map(value => ({
        value,
        label: t(value === 'zh' ? 'lang.zh' : 'lang.en'),
      }))}
      onChange={setLang}
    />
  )
}

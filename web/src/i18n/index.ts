import { createI18n } from 'vue-i18n'
import zh from './zh'
import en from './en'

const i18n = createI18n({
  legacy: false,
  locale: 'zh',
  fallbackLocale: 'zh',
  messages: { zh, en },
})

export default i18n

/**
 * Translate a schema-level display name (e.g., "瓶盖（唇釉/唇彩）" -> "Cap")
 * Falls back to the original name if no translation found.
 */
export function translateName(name: string, locale: string): string {
  if (locale === 'zh') return name
  const msgs = en.names as Record<string, string>
  return msgs[name] || name
}

import { useI18n } from '../context/I18nContext'

export default function LangSwitch() {
  const { lang, setLang } = useI18n()
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 4, marginBottom: 6 }}>
      {['es', 'en', 'pt'].map(l => (
        <button key={l} type="button" onClick={() => setLang(l)}
          style={{ border: 0, borderRadius: 4, padding: '4px 8px', fontSize: 12, letterSpacing: 1,
            fontWeight: 700, background: lang === l ? 'var(--active)' : 'transparent',
            color: lang === l ? 'var(--brand-dark)' : 'var(--muted)' }}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  )
}
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import dictionary from '../i18n/dictionary'
import { I18nProvider, useI18n } from '../context/I18nContext'
import { errText } from '../components/ui'

function Probe() {
  const { t, setLang } = useI18n()
  return (
    <>
      {['es', 'en', 'pt'].map(l => <button key={l} onClick={() => setLang(l)}>{l}</button>)}
      <p data-testid="save">{t('Guardar')}</p>
      <p data-testid="vars">{t('{name} se unió a la conversación', { name: 'Sofía' })}</p>
    </>
  )
}

async function setup() {
  render(<I18nProvider><Probe /></I18nProvider>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'es' })) // el idioma persiste entre tests
  return user
}
const lang = (user, l) => user.click(screen.getByRole('button', { name: l }))

describe('i18n', () => {
  it('cambia entre ES, EN y PT y actualiza <html lang> y localStorage', async () => {
    const user = await setup()
    expect(screen.getByTestId('save')).toHaveTextContent('Guardar')
    await lang(user, 'en')
    expect(screen.getByTestId('save')).toHaveTextContent('Save')
    expect(document.documentElement.lang).toBe('en')
    expect(localStorage.getItem('lang')).toBe('en')
    await lang(user, 'pt')
    expect(screen.getByTestId('save')).toHaveTextContent('Salvar')
  })

  it('interpola variables', async () => {
    const user = await setup()
    expect(screen.getByTestId('vars')).toHaveTextContent('Sofía se unió a la conversación')
    await lang(user, 'en')
    expect(screen.getByTestId('vars')).toHaveTextContent('Sofía joined the conversation')
  })

  it('errText traduce por código de error y conserva el mensaje en español', async () => {
    const user = await setup()
    const e = { code: 'AUTH_INVALID_CREDENTIALS', message: 'Email o contraseña incorrectos.' }
    expect(errText(e)).toBe('Email o contraseña incorrectos. (AUTH_INVALID_CREDENTIALS)')
    await lang(user, 'en')
    expect(errText(e)).toBe('Incorrect email or password. (AUTH_INVALID_CREDENTIALS)')
  })

  it('cada entrada del diccionario tiene EN y PT con las mismas variables', () => {
    const vars = s => (s.match(/\{\w+\}/g) || []).sort().join()
    for (const [key, val] of Object.entries(dictionary)) {
      const [en, pt] = Array.isArray(val) ? val : [val.en, val.pt]
      expect(en, `EN vacío: ${key}`).toBeTruthy()
      expect(pt, `PT vacío: ${key}`).toBeTruthy()
      if (!key.startsWith('code:')) {
        expect(vars(en), `variables EN: ${key}`).toBe(vars(key))
        expect(vars(pt), `variables PT: ${key}`).toBe(vars(key))
      }
    }
  })

  it('todo texto pasado a t() en el código existe en el diccionario', () => {
    const sources = import.meta.glob(['../**/*.jsx', '!../test/**'],
      { query: '?raw', import: 'default', eager: true })
    const used = new Set()
    for (const src of Object.values(sources)) {
      for (const m of src.matchAll(/\bt\(\s*'((?:[^'\\]|\\.)*)'/g)) used.add(m[1])
    }
    expect(used.size).toBeGreaterThan(100)
    expect([...used].filter(k => !(k in dictionary))).toEqual([])
  })
})

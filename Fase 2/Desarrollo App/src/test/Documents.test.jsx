import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Documents from '../pages/company/Documents'
import { fail, json, mockFetch, renderApp } from './utils'

const doc = (over = {}) => ({
  document_id: 'd1', filename: 'guia_examenes.txt', chat_type: 'technical', size_bytes: 120,
  status: 'indexed', progress_pct: 100, chunks: 3, uploaded_at: '2026-01-01T00:00:00Z',
  indexed_at: '2026-01-01T00:00:01Z', error_detail: null, version: 1, ...over })
const list = items => ({ items, page: 1, page_size: 100, total: items.length })
const open = () => renderApp({ '/company/documents': <Documents /> }, '/company/documents')
const fileInput = () => document.querySelector('input[type="file"]')
const txt = () => new File(['contenido de prueba'], 'manual.txt', { type: 'text/plain' })
const created = () => json({ document_id: 'd9', filename: 'manual.txt', status: 'queued' }, 201)

describe('Documentos', () => {
  it('lista los documentos con su estado y fragmentos', async () => {
    mockFetch({ 'GET /company/documents': list([doc()]) })
    open()
    expect(await screen.findByText(/guia_examenes\.txt/)).toBeInTheDocument()
    expect(screen.getByText('Indexado')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('muestra el estado vacío', async () => {
    mockFetch({ 'GET /company/documents': list([]) })
    open()
    expect(await screen.findByText('Sin documentos aún.')).toBeInTheDocument()
  })

  it('sube un archivo como chat técnico por defecto y recarga la lista', async () => {
    const f = mockFetch({ 'GET /company/documents': list([]), 'POST /company/documents': created })
    open()
    await screen.findByText('Sin documentos aún.')
    fireEvent.change(fileInput(), { target: { files: [txt()] } })
    expect(await screen.findByText('Documento subido: ingesta en curso')).toBeInTheDocument()
    const { body, headers } = f.called('POST /company/documents')[0].opts
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('chat_type')).toBe('technical')
    expect(body.get('file').name).toBe('manual.txt')
    expect(headers['Content-Type']).toBeUndefined() // el navegador fija el boundary multipart
    await waitFor(() => expect(f.called('GET /company/documents')).toHaveLength(2))
  })

  it('sube el archivo con el tipo de chat elegido', async () => {
    const f = mockFetch({ 'GET /company/documents': list([]), 'POST /company/documents': created })
    const user = userEvent.setup()
    open()
    await screen.findByText('Sin documentos aún.')
    await user.selectOptions(screen.getAllByRole('combobox')[0], 'commercial')
    fireEvent.change(fileInput(), { target: { files: [txt()] } })
    await screen.findByText('Documento subido: ingesta en curso')
    expect(f.called('POST /company/documents')[0].opts.body.get('chat_type')).toBe('commercial')
  })

  it('muestra el error del backend si el archivo no es válido', async () => {
    mockFetch({
      'GET /company/documents': list([]),
      'POST /company/documents': fail(415, 'FILE_TYPE_UNSUPPORTED', 'Solo se admiten PDF, DOCX, TXT y MD.'),
    })
    open()
    await screen.findByText('Sin documentos aún.')
    fireEvent.change(fileInput(), { target: { files: [txt()] } })
    expect(await screen.findByText(/Solo se admiten PDF, DOCX, TXT y MD/)).toBeInTheDocument()
  })

  it('permite reintentar un documento con error', async () => {
    const f = mockFetch({
      'GET /company/documents': list([doc({ status: 'error', chunks: 0,
        error_detail: 'No se pudo extraer texto del documento.' })]),
      'POST /company/documents/d1/reingest': () => json({ status: 'queued' }, 202),
    })
    const user = userEvent.setup()
    open()
    expect(await screen.findByText('No se pudo extraer texto del documento.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(f.called('POST /company/documents/d1/reingest')).toHaveLength(1))
  })

  it('elimina un documento tras confirmar', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const f = mockFetch({
      'GET /company/documents': list([doc()]),
      'DELETE /company/documents/d1': () => json(null, 204),
    })
    const user = userEvent.setup()
    open()
    await screen.findByText(/guia_examenes\.txt/)
    await user.click(screen.getByRole('button', { name: '🗑' }))
    await waitFor(() => expect(f.called('DELETE /company/documents/d1')).toHaveLength(1))
  })
})

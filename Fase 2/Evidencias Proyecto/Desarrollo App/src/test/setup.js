import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'

// WebSocket falso: guarda las instancias para poder simular mensajes del servidor
class FakeWebSocket {
  static instances = []
  constructor(url) { this.url = url; FakeWebSocket.instances.push(this) }
  send() {}
  close() {}
}
globalThis.WebSocket = FakeWebSocket

beforeEach(() => { FakeWebSocket.instances.length = 0 })

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  localStorage.clear()
})

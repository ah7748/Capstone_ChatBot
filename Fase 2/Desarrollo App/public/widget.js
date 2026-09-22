/* Widget embebible del Chatbot de Soporte Genérico (Alloxentric).
 * Uso: <script src="https://soporte.allox.ai/widget.js" data-tenant="wellq" async></script>
 * API: window.AlloxChat = { open, close, toggle, identify, setLang, on, destroy }
 * Evento de inicio: window "allox:ready".                                         */
(function () {
  var script = document.currentScript
  if (!script) return
  var tenant = script.dataset.tenant
  if (!tenant) { console.error('[AlloxChat] Falta data-tenant'); return }

  var base = script.src.replace(/\/widget\.js.*$/, '')
  var lang = script.dataset.lang || ''
  var color = script.dataset.color || '#00a79d'
  var position = script.dataset.position === 'bottom-left' ? 'left' : 'right'
  var zindex = script.dataset.zindex || 999999
  var listeners = {}
  var opened = false

  // burbuja flotante
  var btn = document.createElement('button')
  btn.setAttribute('aria-label', 'Chat de soporte')
  btn.innerHTML = '💬'
  btn.style.cssText = 'position:fixed;bottom:22px;' + position + ':22px;width:58px;height:58px;' +
    'border-radius:50%;border:0;background:' + color + ';color:#fff;font-size:24px;cursor:pointer;' +
    'box-shadow:0 8px 24px rgba(0,0,0,.25);z-index:' + zindex + ';transition:transform .15s'
  btn.onmouseenter = function () { btn.style.transform = 'scale(1.08)' }
  btn.onmouseleave = function () { btn.style.transform = 'scale(1)' }

  // iframe con el chat (la página /c/{slug}?embed=1 de la SPA)
  var frame = document.createElement('iframe')
  frame.src = base + '/c/' + tenant + '?embed=1' + (lang ? '&lang=' + lang : '')
  frame.title = 'Chat de soporte'
  frame.style.cssText = 'position:fixed;bottom:92px;' + position + ':22px;width:380px;height:560px;' +
    'max-height:calc(100vh - 120px);max-width:calc(100vw - 44px);border:0;border-radius:16px;' +
    'box-shadow:0 12px 40px rgba(0,0,0,.3);z-index:' + zindex + ';display:none;background:#fff'

  function emit(name, data) {
    (listeners[name] || []).forEach(function (fn) { try { fn(data) } catch (e) { /* noop */ } })
  }
  function open() { frame.style.display = 'block'; opened = true; emit('open') }
  function close() { frame.style.display = 'none'; opened = false; emit('close') }

  btn.onclick = function () { opened ? close() : open() }

  window.addEventListener('message', function (ev) {
    var d = ev.data || {}
    if (d.allox === 'escalated') emit('escalated', { mode: d.mode })
    if (d.allox === 'message') emit('message')
  })

  var pendingUser = null
  window.AlloxChat = {
    open: open,
    close: close,
    toggle: function () { opened ? close() : open() },
    identify: function (user) {
      pendingUser = user
      frame.contentWindow && frame.contentWindow.postMessage({ allox: 'identify', user: user }, '*')
    },
    setLang: function (l) {
      frame.src = base + '/c/' + tenant + '?embed=1&lang=' + l
    },
    on: function (name, fn) { (listeners[name] = listeners[name] || []).push(fn) },
    destroy: function () { btn.remove(); frame.remove(); delete window.AlloxChat },
  }

  frame.addEventListener('load', function () {
    if (pendingUser) window.AlloxChat.identify(pendingUser)
  })

  function mount() {
    document.body.appendChild(btn)
    document.body.appendChild(frame)
    if (script.dataset.open === 'true') open()
    window.dispatchEvent(new Event('allox:ready'))
  }
  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', mount)
    : mount()
})()

const { spawn } = require('node:child_process')
const fs = require('node:fs')

const chrome = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const profile = 'G:/AiCad/artifacts/showroom/chrome-profile-cdp'
const port = 9227
const url = 'http://127.0.0.1:8010/?mode=showroom'

fs.rmSync(profile, { recursive: true, force: true })

const browser = spawn(chrome, [
  '--headless=new',
  '--disable-gpu',
  '--disable-crash-reporter',
  '--disable-breakpad',
  '--no-first-run',
  '--no-default-browser-check',
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  '--window-size=1440,900',
  url,
], { stdio: 'ignore' })

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function waitForTab() {
  for (let i = 0; i < 50; i += 1) {
    try {
      const tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json()
      const tab = tabs.find((entry) => entry.url.includes('mode=showroom')) || tabs[0]
      if (tab?.webSocketDebuggerUrl) return tab
    } catch {
      // Chrome is still starting.
    }
    await sleep(250)
  }
  throw new Error('No Chrome DevTools tab available')
}

async function connect(tab) {
  const socket = new WebSocket(tab.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => {
    socket.onopen = resolve
    socket.onerror = reject
  })

  let id = 0
  const pending = new Map()
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data)
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message)
      pending.delete(message.id)
    }
  }

  return {
    socket,
    send(method, params = {}) {
      return new Promise((resolve) => {
        const messageId = ++id
        pending.set(messageId, resolve)
        socket.send(JSON.stringify({ id: messageId, method, params }))
      })
    },
  }
}

async function main() {
  try {
    const tab = await waitForTab()
    const cdp = await connect(tab)
    await cdp.send('Runtime.enable')
    await sleep(3500)

    await cdp.send('Input.dispatchKeyEvent', {
      type: 'keyDown',
      code: 'KeyW',
      key: 'w',
      windowsVirtualKeyCode: 87,
      nativeVirtualKeyCode: 87,
    })
    await sleep(3200)
    await cdp.send('Input.dispatchKeyEvent', {
      type: 'keyUp',
      code: 'KeyW',
      key: 'w',
      windowsVirtualKeyCode: 87,
      nativeVirtualKeyCode: 87,
    })
    await sleep(1200)

    const expression = `JSON.stringify({
      href: location.href,
      hasCanvas: !!document.querySelector('canvas'),
      canvasCount: document.querySelectorAll('canvas').length,
      stats: window.__showroomStats || null,
      assetError: window.__showroomAssetError || null,
      body: document.body.innerText.slice(0, 120)
    })`
    const result = await cdp.send('Runtime.evaluate', { expression, returnByValue: true })
    console.log(result.result.result.value)
    cdp.socket.close()
  } finally {
    browser.kill()
  }
}

main().catch((error) => {
  console.error(error)
  browser.kill()
  process.exit(1)
})

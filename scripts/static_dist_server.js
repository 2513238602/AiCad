const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const { spawnSync } = require('node:child_process')

const args = new Map()
for (let i = 2; i < process.argv.length; i += 2) {
  args.set(process.argv[i], process.argv[i + 1])
}

const host = args.get('--host') || '127.0.0.1'
const port = Number(args.get('--port') || 8010)
const projectRoot = path.resolve(__dirname, '..')
const root = path.join(projectRoot, 'web', 'dist')
const artifactsRoot = path.join(projectRoot, 'artifacts')
const prebuiltRoot = path.join(artifactsRoot, 'gallery_prebuilt')
const pictureRoot = path.join(projectRoot, 'tests', 'picture')
const srcRoot = path.join(projectRoot, 'src')
const pythonExe = process.env.AICAD_PYTHON
  || path.join(os.homedir(), '.conda', 'envs', 'AiCad', 'python.exe')

const types = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
  '.stl': 'model/stl',
  '.step': 'application/step',
  '.stp': 'application/step',
  '.glb': 'model/gltf-binary',
  '.gltf': 'model/gltf+json',
}

const renderMetadataCache = new Map()
let schemaCache = null

function sendJson(res, code, obj) {
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-cache',
  })
  res.end(JSON.stringify(obj, null, 2))
}

function safePath(base, urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0]).replace(/^\/+/, '')
  const file = path.resolve(base, clean || 'index.html')
  if (!file.startsWith(base)) return null
  return file
}

function sendFile(res, base, relPath, fallbackToIndex = false) {
  let file = safePath(base, relPath)
  if (!file) {
    res.writeHead(403)
    res.end('Forbidden')
    return
  }

  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    if (!fallbackToIndex) {
      res.writeHead(404)
      res.end('Not found')
      return
    }
    file = path.join(base, 'index.html')
  }

  fs.readFile(file, (error, data) => {
    if (error) {
      res.writeHead(404)
      res.end('Not found')
      return
    }
    res.writeHead(200, {
      'Content-Type': types[path.extname(file).toLowerCase()] || 'application/octet-stream',
      'Cache-Control': 'no-cache',
    })
    res.end(data)
  })
}

function firstImage(catId) {
  const dir = path.join(pictureRoot, catId)
  if (!fs.existsSync(dir)) return null
  const found = fs.readdirSync(dir)
    .filter((name) => ['.jpg', '.jpeg', '.png', '.webp'].includes(path.extname(name).toLowerCase()))
    .sort((a, b) => a.localeCompare(b))[0]
  return found || null
}

function readManifest(catId) {
  const file = path.join(prebuiltRoot, catId, 'manifest.json')
  if (!fs.existsSync(file)) return null
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return null
  }
}

function galleryItems() {
  if (!fs.existsSync(prebuiltRoot)) return []
  return fs.readdirSync(prebuiltRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => {
      const catId = entry.name
      const manifest = readManifest(catId)
      const image = firstImage(catId)
      return {
        cat_id: catId,
        desc: manifest?.desc || catId,
        thumbnail: image ? `/gallery/images/${catId}/${image}` : null,
        image_count: image ? fs.readdirSync(path.join(pictureRoot, catId))
          .filter((name) => ['.jpg', '.jpeg', '.png', '.webp'].includes(path.extname(name).toLowerCase())).length : 0,
        prebuilt: Boolean(manifest),
      }
    })
    .filter((item) => item.prebuilt && !item.cat_id.includes('__custom'))
    .sort((a, b) => a.cat_id.localeCompare(b.cat_id))
}

function renderMetadata(catId) {
  if (renderMetadataCache.has(catId)) return renderMetadataCache.get(catId)
  let metadata = {}
  if (fs.existsSync(pythonExe)) {
    const code = [
      'import json, sys',
      `sys.path.insert(0, r"${srcRoot}")`,
      'from core.render_materials import build_gallery_render_metadata',
      `meta = build_gallery_render_metadata(r"${projectRoot}", ${JSON.stringify(catId)})`,
      'print(json.dumps(meta, ensure_ascii=False))',
    ].join('; ')
    const out = spawnSync(pythonExe, ['-c', code], {
      cwd: projectRoot,
      encoding: 'utf8',
      timeout: 15000,
      windowsHide: true,
    })
    if (out.status === 0 && out.stdout.trim()) {
      try {
        metadata = JSON.parse(out.stdout)
      } catch {
        metadata = {}
      }
    }
  }
  renderMetadataCache.set(catId, metadata)
  return metadata
}

function withRenderParams(params, compId, metadata) {
  const out = { ...(params || {}) }
  const prefix = `_render_${compId}_`
  for (const [key, value] of Object.entries(metadata || {})) {
    if (key.startsWith(prefix)) out[key] = value
  }
  return out
}

function handleGalleryPrebuilt(res, catId) {
  const manifest = readManifest(catId)
  if (!manifest) return sendJson(res, 404, { error: 'prebuilt not found', cat_id: catId })

  const metadata = renderMetadata(catId)
  const results = {}
  for (const [compId, compData] of Object.entries(manifest.components || {})) {
    if (!compData?.stl) continue
    const stlPath = path.join(prebuiltRoot, catId, compData.stl)
    if (!fs.existsSync(stlPath)) continue
    results[compId] = {
      ok: true,
      stl_url: `/artifacts/gallery_prebuilt/${catId}/${compData.stl}`,
      step_url: compData.step ? `/artifacts/gallery_prebuilt/${catId}/${compData.step}` : undefined,
      qc: {
        params: withRenderParams(compData.params || {}, compId, metadata),
      },
    }
  }

  const positions = {}
  for (const [cid, val] of Object.entries(manifest.assembly_positions || {})) {
    positions[cid] = typeof val === 'object' ? val : { dz: Number(val) || 0, description: '' }
  }
  return sendJson(res, 200, {
    ok: true,
    cat_id: catId,
    results,
    assembly: { positions },
  })
}

function minimalSchema() {
  return {
    products: [
      {
        id: 'lip_gloss',
        name: 'Lip Gloss',
        components: ['bottle', 'cap', 'wand', 'wiper'].map((id) => ({
          id,
          name: id,
          desc: id,
          enabled: true,
          params: [],
          style_presets: [],
        })),
      },
    ],
  }
}

function loadSchema() {
  if (schemaCache) return schemaCache
  if (!fs.existsSync(pythonExe)) return minimalSchema()

  const code = [
    'import json, sys',
    `sys.path.insert(0, ${JSON.stringify(srcRoot)})`,
    'from products.lip_gloss.components.registry import schema',
    'print(json.dumps(schema(), ensure_ascii=False))',
  ].join('; ')
  const out = spawnSync(pythonExe, ['-c', code], {
    cwd: projectRoot,
    encoding: 'utf8',
    timeout: 20000,
    windowsHide: true,
    env: {
      ...process.env,
      PYTHONIOENCODING: 'utf-8',
    },
  })
  if (out.status === 0 && out.stdout.trim()) {
    try {
      schemaCache = JSON.parse(out.stdout)
      return schemaCache
    } catch (error) {
      console.warn('[static-dist] schema parse failed:', error)
    }
  } else {
    console.warn('[static-dist] schema load failed:', (out.stderr || '').trim() || `exit ${out.status}`)
  }
  return minimalSchema()
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url || '/', `http://${host}:${port}`)

  if (url.pathname === '/api/schema') {
    return sendJson(res, 200, loadSchema())
  }
  if (url.pathname === '/api/generated' && req.method === 'DELETE') {
    return sendJson(res, 200, { ok: true })
  }
  if (url.pathname.startsWith('/api/generated/')) {
    return sendJson(res, 200, { ok: true })
  }
  if (url.pathname === '/api/derived_rules' || url.pathname === '/api/state') {
    return sendJson(res, 200, {})
  }
  if (url.pathname === '/api/gallery') {
    return sendJson(res, 200, { items: galleryItems() })
  }
  if (url.pathname.startsWith('/api/gallery/prebuilt/')) {
    return handleGalleryPrebuilt(res, decodeURIComponent(url.pathname.split('/').pop() || ''))
  }
  if (url.pathname.startsWith('/api/gallery/generate/')) {
    return handleGalleryPrebuilt(res, decodeURIComponent(url.pathname.split('/').pop() || ''))
  }
  if (url.pathname.startsWith('/artifacts/')) {
    return sendFile(res, artifactsRoot, url.pathname.slice('/artifacts/'.length))
  }
  if (url.pathname.startsWith('/gallery/images/')) {
    return sendFile(res, pictureRoot, url.pathname.slice('/gallery/images/'.length))
  }

  return sendFile(res, root, url.pathname, true)
})

server.listen(port, host, () => {
  console.log(`[static-dist] http://${host}:${port}`)
  console.log(`[static-dist] root=${root}`)
})

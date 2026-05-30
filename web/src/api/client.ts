import type { Schema, GenerateResponse, CrossConstraintMap, ProfileConstraints, DragHandle, GalleryItem, GalleryGenerateResponse, ShowroomManifest, ExoticPreset, ExoticCapGenerateResponse } from './types'

const BASE = ''

export async function fetchSchema(): Promise<Schema> {
  const r = await fetch(`${BASE}/api/schema`)
  if (!r.ok) throw new Error(`Schema fetch failed: ${r.status}`)
  return r.json()
}

export async function fetchDerivedRules(): Promise<Record<string, any>> {
  const r = await fetch(`${BASE}/api/derived_rules`)
  if (!r.ok) return {}
  return r.json()
}

export async function fetchConstraints(componentId: string): Promise<CrossConstraintMap> {
  try {
    const r = await fetch(`${BASE}/api/constraints/${componentId}`)
    if (!r.ok) return {}
    const data = await r.json()
    return data.constraints || {}
  } catch (e) {
    console.warn('fetchConstraints error:', e)
    return {}
  }
}

export async function fetchState(): Promise<Record<string, any>> {
  const r = await fetch(`${BASE}/api/state`)
  if (!r.ok) return {}
  return r.json()
}

export async function generate(payload: {
  product: string
  component: string
  preset_id: string | null
  params: Record<string, any>
  title: string
}): Promise<GenerateResponse> {
  const r = await fetch(`${BASE}/api/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!r.ok) {
    const errBody = await r.json().catch(() => ({}))
    throw new Error(errBody.error || `HTTP ${r.status}`)
  }
  return r.json()
}

export async function deleteGeneratedComponent(componentId: string): Promise<void> {
  await fetch(`${BASE}/api/generated/${componentId}`, { method: 'DELETE' })
}

export async function deleteAllGenerated(): Promise<void> {
  await fetch(`${BASE}/api/generated`, { method: 'DELETE' })
}

export async function storeGeneratedComponent(
  componentId: string,
  params: Record<string, any>,
): Promise<void> {
  await fetch(`${BASE}/api/generated/${componentId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export async function rebuild(): Promise<{ ok: boolean; message?: string; error?: string }> {
  const r = await fetch(`${BASE}/api/rebuild`, { method: 'POST' })
  return r.json()
}

export async function fetchDragHandles(
  componentId: string,
  params: Record<string, any>,
): Promise<DragHandle[]> {
  try {
    const qs = encodeURIComponent(JSON.stringify(params))
    const r = await fetch(`${BASE}/api/drag_handles/${componentId}?params=${qs}`)
    if (!r.ok) return []
    const data = await r.json()
    return data.handles || []
  } catch {
    return []
  }
}

export async function fetchProfileConstraints(
  componentId: string,
  params: Record<string, any>,
): Promise<ProfileConstraints | null> {
  try {
    const qs = encodeURIComponent(JSON.stringify(params))
    const r = await fetch(`${BASE}/api/profile_constraints/${componentId}?params=${qs}`)
    if (!r.ok) return null
    return r.json()
  } catch {
    return null
  }
}

export async function fetchGallery(): Promise<{ items: GalleryItem[] }> {
  const r = await fetch(`${BASE}/api/gallery`)
  if (!r.ok) throw new Error(`Gallery fetch failed: ${r.status}`)
  return r.json()
}

export async function generateGalleryItem(catId: string): Promise<GalleryGenerateResponse> {
  const r = await fetch(`${BASE}/api/gallery/generate/${catId}`, { method: 'POST' })
  return r.json()
}

export async function fetchGalleryPrebuilt(catId: string): Promise<GalleryGenerateResponse> {
  const r = await fetch(`${BASE}/api/gallery/prebuilt/${catId}`)
  return r.json()
}

export async function fetchShowroomManifest(): Promise<ShowroomManifest> {
  const r = await fetch(`${BASE}/artifacts/showroom/manifest.json`)
  if (!r.ok) throw new Error(`Showroom manifest fetch failed: ${r.status}`)
  return r.json()
}

export async function fetchAssemblyReport(
  componentIds?: string[],
): Promise<Record<string, any>> {
  try {
    let url = `${BASE}/api/assembly`
    if (componentIds && componentIds.length > 0) {
      url += `?components=${componentIds.join(',')}`
    }
    const r = await fetch(url)
    if (!r.ok) return {}
    return r.json()
  } catch {
    return {}
  }
}

// ── Exotic Cap API ──

export async function fetchExoticPresets(): Promise<ExoticPreset[]> {
  try {
    const r = await fetch(`${BASE}/api/exotic_cap/presets`)
    if (!r.ok) return []
    const data = await r.json()
    return data.presets || []
  } catch {
    return []
  }
}

export async function generateExoticCap(payload: {
  preset_id: string
  target_od_mm?: number
  target_height_mm?: number | null
  inner_radius_mm?: number | null
  cavity_depth_mm?: number | null
}): Promise<ExoticCapGenerateResponse> {
  const r = await fetch(`${BASE}/api/exotic_cap/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!r.ok) {
    const errBody = await r.json().catch(() => ({}))
    throw new Error(errBody.error || `HTTP ${r.status}`)
  }
  return r.json()
}

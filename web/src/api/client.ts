import type { Schema, GenerateResponse, CrossConstraintMap } from './types'

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

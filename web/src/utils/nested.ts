/**
 * Set a value in a nested object by dotted key path.
 * Creates intermediate objects as needed.
 */
export function setNested(obj: Record<string, any>, dottedKey: string, val: any): void {
  const parts = dottedKey.split('.')
  let cur = obj
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i]
    if (i === parts.length - 1) {
      cur[p] = val
    } else {
      if (!cur[p] || typeof cur[p] !== 'object') cur[p] = {}
      cur = cur[p]
    }
  }
}

/**
 * Delete a value from a nested object by dotted key path.
 */
export function deleteNested(obj: Record<string, any>, dottedKey: string): void {
  const parts = dottedKey.split('.')
  let cur: any = obj
  for (let i = 0; i < parts.length - 1; i++) {
    const p = parts[i]
    if (!cur || typeof cur !== 'object' || !(p in cur)) return
    cur = cur[p]
  }
  if (cur && typeof cur === 'object') {
    delete cur[parts[parts.length - 1]]
  }
}

/**
 * Get a value from a nested object by dotted key path.
 */
export function getNested(obj: Record<string, any>, dottedKey: string, fallback?: any): any {
  const parts = dottedKey.split('.')
  let cur: any = obj
  for (const p of parts) {
    if (!cur || typeof cur !== 'object' || !(p in cur)) return fallback
    cur = cur[p]
  }
  return cur
}

/**
 * Flatten a nested object into a flat object with dotted keys.
 */
export function flattenNested(obj: Record<string, any>, prefix = ''): Record<string, any> {
  const out: Record<string, any> = {}
  if (!obj || typeof obj !== 'object') return out
  for (const [k, v] of Object.entries(obj)) {
    const kk = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(out, flattenNested(v, kk))
    } else {
      out[kk] = v
    }
  }
  return out
}

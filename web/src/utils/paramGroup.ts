/**
 * Group ordering and groupOf() logic for parameter panel organization.
 */

// Group keys (language-independent) - translations are in i18n files
export const GROUP_KEYS = [
  'outer',
  'inner',
  'thread',
  'seal',
  'grip',
  'knurl',
  'logo',
  'finish',
  'other',
] as const

export type GroupKey = (typeof GROUP_KEYS)[number]

// Group priority order (lower = higher priority)
export const GROUP_ORDER: Record<string, number> = {
  outer: 1,
  inner: 2,
  thread: 3,
  seal: 4,
  grip: 5,
  knurl: 6,
  logo: 7,
  finish: 8,
  other: 99,
}

/**
 * Determine which group a parameter belongs to, based on its key.
 */
export function groupOf(k: string): GroupKey {
  // Outer shape
  if (
    k === 'outer_od_mm' ||
    k === 'height_mm' ||
    k === 'taper_deg' ||
    k === 'top_shape' ||
    k === 'body_od_mm' ||
    k === 'neck_od_mm' ||
    k === 'neck_height_mm' ||
    k === 'total_height_mm' ||
    k === 'cap_height_mm'
  )
    return 'outer'

  // Inner structure
  if (
    k === 'inner_id_mm' ||
    k === 'cavity_depth_mm' ||
    k === 'edge_fillet_mm' ||
    k === 'inner_depth_mm' ||
    k === 'wall_thickness_mm' ||
    k === 'bottom_thickness_mm' ||
    k === 'lip_thickness_mm' ||
    k === 'shoulder_height_mm' ||
    k === 'orifice_mm' ||
    k === 'stem_diameter_mm' ||
    k === 'stem_length_mm' ||
    k === 'mouth_to_top_mm'
  )
    return 'inner'

  // Prefix-based matching
  if (k.startsWith('thread.')) return 'thread'
  if (k.startsWith('seal.')) return 'seal'
  if (k.startsWith('grip.')) return 'grip'
  if (k.startsWith('knurl.')) return 'knurl'
  if (k.startsWith('logo.')) return 'logo'
  if (k.startsWith('brush.')) return 'other'
  if (k.startsWith('seal_ring.')) return 'seal'
  if (k.startsWith('flange_')) return 'inner'

  // Fallback prefix matching
  if (k.startsWith('outer_') || k.includes('corner_') || k.includes('chamfer')) return 'outer'
  if (k.startsWith('inner_') || k.startsWith('wall_') || k.includes('cavity')) return 'inner'

  // Finish / spec
  if (k === 'finish') return 'finish'

  return 'other'
}

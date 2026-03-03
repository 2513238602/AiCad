<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import { useSchemaStore } from '@/stores/schema'
import { useParamsStore } from '@/stores/params'
import { useGenerate } from '@/composables/useGenerate'
import { flattenNested } from '@/utils/nested'
import { inferParamDef } from '@/utils/cast'
import { groupOf, GROUP_ORDER } from '@/utils/paramGroup'
import type { ParamDef } from '@/api/types'
import ParamGroup from '@/components/param/ParamGroup.vue'

const { t } = useI18n()
const appStore = useAppStore()
const schemaStore = useSchemaStore()
const paramsStore = useParamsStore()
const { scheduleAutoGenerate } = useGenerate()

// Extended param def with original index
interface ParamDefEx extends ParamDef {
  _origIdx: number
}

// Build param definitions from schema + preset + current state
const paramGroups = computed(() => {
  const comp = schemaStore.currentComponent
  if (!comp) return {}

  // Start with schema defs
  const defsFromSchema: ParamDefEx[] = (comp.params || []).map((x, i) => ({
    ...x,
    _origIdx: i,
  }))
  const defMap: Record<string, ParamDefEx> = {}
  for (const d of defsFromSchema) defMap[d.k] = d

  // Merge with preset + current state values
  const preset = schemaStore.currentPreset
  const seed: Record<string, any> = {}
  if (preset?.params) {
    for (const [k, v] of Object.entries(preset.params)) seed[k] = v
  }
  const flatNow = flattenNested(paramsStore.values)
  for (const [k, v] of Object.entries(flatNow)) seed[k] = v

  let nextIdx = defsFromSchema.length
  for (const [k, v] of Object.entries(seed)) {
    if (!(k in defMap)) {
      const inferred = inferParamDef(k, v)
      defMap[k] = { ...inferred, _origIdx: nextIdx++ }
    }
  }

  let defs = Object.values(defMap)

  // Filter by search text
  const ft = (appStore.filterText || '').trim().toLowerCase()
  if (ft) {
    defs = defs.filter(
      (d) =>
        (d.k || '').toLowerCase().includes(ft) || (d.name || '').toLowerCase().includes(ft),
    )
  }

  // Sort by group priority, then original index
  defs.sort((a, b) => {
    const ga = groupOf(a.k)
    const gb = groupOf(b.k)
    const oa = GROUP_ORDER[ga] || 99
    const ob = GROUP_ORDER[gb] || 99
    if (oa !== ob) return oa - ob
    return (a._origIdx || 0) - (b._origIdx || 0)
  })

  // Group params
  const groups: Record<string, ParamDefEx[]> = {}
  for (const d of defs) {
    const g = groupOf(d.k)
    if (!groups[g]) groups[g] = []
    groups[g].push(d)
  }

  return groups
})

// All groups expanded by default
const activeGroups = ref<string[]>([])

// When paramGroups changes (e.g. component switch), expand all groups
watch(
  () => Object.keys(paramGroups.value),
  (keys) => {
    activeGroups.value = [...keys]
  },
  { immediate: true },
)

function getGroupLabel(groupKey: string): string {
  return t(`groups.${groupKey}`)
}
</script>

<template>
  <div class="card right-panel">
    <div class="section-title">{{ t('ui.sectionParams') }}</div>
    <div class="param-scroll">
      <el-collapse v-model="activeGroups">
        <ParamGroup
          v-for="(items, groupKey) in paramGroups"
          :key="groupKey"
          :group-key="String(groupKey)"
          :group-label="getGroupLabel(String(groupKey))"
          :params="items"
        />
      </el-collapse>
    </div>
  </div>
</template>

<style scoped>
.right-panel {
  min-height: 200px;
}

.param-scroll {
  max-height: calc(100vh - 180px);
  overflow-y: auto;
  padding-right: 4px;
}

/* Custom scrollbar */
.param-scroll::-webkit-scrollbar {
  width: 5px;
}
.param-scroll::-webkit-scrollbar-track {
  background: transparent;
}
.param-scroll::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}
.param-scroll::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>

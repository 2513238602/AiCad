<script setup lang="ts">
import { computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import { useParamsStore } from '@/stores/params'
import { useGenerate } from '@/composables/useGenerate'
import {
  isDerivedParam,
  isDerivedReadonly,
  getDerivedDesc,
  computeDerivedDefault,
  computeDerivedRange,
  updateDerivedParams,
} from '@/composables/useDerivedRules'
import { getNested } from '@/utils/nested'
import { translateName } from '@/i18n'
import type { ParamDef, CrossConstraint } from '@/api/types'
import { dlog } from '@/utils/debugLog'
import ProfileEditor from './ProfileEditor.vue'

const props = defineProps<{
  paramDef: ParamDef
}>()

const { t, locale } = useI18n()
const appStore = useAppStore()
const paramsStore = useParamsStore()
const { scheduleAutoGenerate } = useGenerate()

const componentId = computed(() => appStore.componentId || '')
const d = computed(() => props.paramDef)

// Derived param status
const derived = computed(() => isDerivedParam(componentId.value, d.value.k))
const derivedReadonly = computed(() => isDerivedReadonly(componentId.value, d.value.k))
const derivedDesc = computed(() => getDerivedDesc(componentId.value, d.value.k))

// Cross-component constraint
const crossConstraint = computed<CrossConstraint | null>(
  () => paramsStore.crossConstraints[d.value.k] || null,
)
const isLocked = computed(() => crossConstraint.value?.locked ?? false)
const isReadonly = computed(() => derivedReadonly.value || isLocked.value)

// Whether current component is in spline profile mode
const isSplineMode = computed(() => {
  return getNested(paramsStore.values, 'profile_mode', 'classic') === 'spline'
})

// Display name
const displayName = computed(() => {
  const paramI18nKey = `params.${d.value.k}`
  const paramName = t(paramI18nKey)
  // If i18n has a translation, use it; otherwise use schema name
  if (paramName !== paramI18nKey) return paramName
  return translateName(d.value.name || d.value.k, locale.value)
})

const unit = computed(() => (d.value.unit ? ` (${d.value.unit})` : ''))

// Enum label translation
function enumLabel(ch: string): string {
  const key = `enums.${ch}`
  const translated = t(key)
  return translated !== key ? translated : ch
}

// Effective range (cross-constraint > derived > schema)
const effectiveMin = computed<number | undefined>(() => {
  if (crossConstraint.value) return crossConstraint.value.constrained_min
  if (derived.value) {
    const range = computeDerivedRange(componentId.value, d.value.k, paramsStore.values)
    if (range) return range[0]
  }
  return d.value.min
})

const effectiveMax = computed<number | undefined>(() => {
  if (crossConstraint.value) return crossConstraint.value.constrained_max
  if (derived.value) {
    const range = computeDerivedRange(componentId.value, d.value.k, paramsStore.values)
    if (range) return range[1]
  }
  return d.value.max
})

// Current value
const currentValue = computed({
  get() {
    const val = getNested(paramsStore.values, d.value.k, undefined)
    if (val !== undefined && val !== null) return val

    // Cross constraint default
    if (crossConstraint.value) return crossConstraint.value.constrained_default

    // Derived default
    if (derived.value) {
      const computed = computeDerivedDefault(componentId.value, d.value.k, paramsStore.values)
      if (computed !== null) return computed
    }

    return d.value.default ?? ''
  },
  set(val: any) {
    applyValue(val)
  },
})

// Slider value (synced with currentValue)
const sliderValue = computed({
  get() {
    const v = currentValue.value
    return typeof v === 'number' ? v : 0
  },
  set(val: number) {
    applyValue(val)
  },
})

// Whether to show slider
const showSlider = computed(() => {
  return (
    (d.value.type === 'float' || d.value.type === 'int') &&
    effectiveMin.value !== undefined &&
    effectiveMax.value !== undefined &&
    !isReadonly.value
  )
})

// Apply a value change
function applyValue(raw: any) {
  let v: any = raw

  if (d.value.type === 'bool') {
    v = raw === true || raw === 'true'
  } else if (d.value.type === 'int') {
    v = parseInt(String(raw), 10)
    if (isNaN(v)) return
  } else if (d.value.type === 'float') {
    v = parseFloat(String(raw))
    if (isNaN(v)) return
  }

  // Clamp to effective range
  if ((d.value.type === 'float' || d.value.type === 'int') && typeof v === 'number') {
    const origV = v
    if (effectiveMin.value !== undefined && v < effectiveMin.value) v = effectiveMin.value
    if (effectiveMax.value !== undefined && v > effectiveMax.value) v = effectiveMax.value
    if (v !== origV) {
      dlog.param(`${d.value.k}: 输入 ${origV} 夹到 ${v} [${effectiveMin.value}, ${effectiveMax.value}]`)
    }
  }

  const oldVal = paramsStore.getParam(d.value.k)
  paramsStore.setParam(d.value.k, v)
  dlog.param(`${d.value.k}: ${oldVal} → ${v}`)

  // If core param changed, update derived params
  if (!derived.value) {
    dlog.derived(`核心参数变化: ${d.value.k}=${v}, 更新派生参数`)
    updateDerivedParams(componentId.value, d.value.k, paramsStore.values, paramsStore.setParam)
  }

  if (appStore.autoGenerate) scheduleAutoGenerate()
}

// Initialize derived param defaults on mount
onMounted(() => {
  const existing = getNested(paramsStore.values, d.value.k, undefined)
  if (existing === undefined || existing === null) {
    if (crossConstraint.value) {
      paramsStore.setParam(d.value.k, crossConstraint.value.constrained_default)
    } else if (derived.value) {
      const computed = computeDerivedDefault(componentId.value, d.value.k, paramsStore.values)
      if (computed !== null) paramsStore.setParam(d.value.k, computed)
    }
  }
})

// Constraint tooltip
const constraintTooltip = computed(() => {
  if (!crossConstraint.value) return ''
  const c = crossConstraint.value
  return `${c.description}\n来源: ${c.source_component}.${c.source_param} = ${c.source_value}`
})
</script>

<template>
  <div class="param-field">
    <div class="param-label">
      <span>{{ displayName }}{{ unit }}</span>
      <span class="badge">{{ d.k }}</span>
      <el-tag v-if="derived && !derivedReadonly" size="small" type="primary" effect="light">
        {{ t('badges.derived') }}
      </el-tag>
      <el-tag v-if="derivedReadonly" size="small" type="info" effect="light">
        {{ t('badges.auto') }}
      </el-tag>
      <el-tooltip v-if="crossConstraint" :content="constraintTooltip" placement="top">
        <el-tag v-if="isLocked" size="small" type="danger" effect="light">
          {{ t('badges.locked') }}
        </el-tag>
        <el-tag v-else size="small" type="warning" effect="light">
          {{ t('badges.constrained') }}
        </el-tag>
      </el-tooltip>
    </div>

    <!-- Enum type -->
    <el-select
      v-if="d.type === 'enum'"
      :model-value="currentValue"
      @update:model-value="applyValue"
      :disabled="isReadonly"
      style="width: 100%"
      size="small"
    >
      <el-option v-for="ch in d.choices || []" :key="ch" :label="enumLabel(ch)" :value="ch" />
    </el-select>

    <!-- Bool type -->
    <el-select
      v-else-if="d.type === 'bool'"
      :model-value="String(currentValue)"
      @update:model-value="(v: string) => applyValue(v === 'true')"
      :disabled="isReadonly"
      style="width: 100%"
      size="small"
    >
      <el-option :label="t('ui.optYes')" value="true" />
      <el-option :label="t('ui.optNo')" value="false" />
    </el-select>

    <!-- Profile points JSON → visual editor (only when profile_mode is spline) -->
    <ProfileEditor
      v-else-if="d.type === 'str' && d.k.endsWith('profile_points_json') && isSplineMode"
      :param-key="d.k"
    />

    <!-- String type -->
    <el-input
      v-else-if="d.type === 'str'"
      :model-value="String(currentValue)"
      @update:model-value="applyValue"
      :disabled="isReadonly"
      size="small"
    />

    <!-- Numeric type with slider -->
    <div v-else class="param-numeric">
      <el-slider
        v-if="showSlider"
        :model-value="sliderValue"
        @update:model-value="applyValue"
        :min="effectiveMin"
        :max="effectiveMax"
        :step="d.step || (d.type === 'int' ? 1 : 0.1)"
        :show-tooltip="true"
        style="flex: 1; margin-right: 12px"
      />
      <el-input-number
        :model-value="typeof currentValue === 'number' ? currentValue : 0"
        @update:model-value="(v: number | undefined) => v !== undefined && applyValue(v)"
        :min="effectiveMin"
        :max="effectiveMax"
        :step="d.step || (d.type === 'int' ? 1 : 0.1)"
        :disabled="isReadonly"
        :controls="false"
        size="small"
        style="width: 90px"
      />
    </div>

    <!-- Derived param hint -->
    <div v-if="derived" class="param-derived-hint">
      {{ derivedDesc }}
    </div>
  </div>
</template>

<style scoped>
.param-field {
  margin-bottom: 14px;
  padding: 8px 10px;
  border-radius: 8px;
  transition: background 0.15s;
}

.param-field:hover {
  background: var(--color-bg-hover, #f8fafc);
}

.param-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary, #475569);
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.param-label > span:first-child {
  color: var(--color-text-primary, #1e293b);
  font-weight: 600;
}

.param-numeric {
  display: flex;
  align-items: center;
  gap: 12px;
}

.param-derived-hint {
  font-size: 11px;
  color: var(--color-accent, #2563eb);
  margin-top: 4px;
  font-weight: 500;
  opacity: 0.85;
}
</style>

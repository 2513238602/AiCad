<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import { useSchemaStore } from '@/stores/schema'
import { useParamsStore } from '@/stores/params'
import { useGenerate } from '@/composables/useGenerate'
import { translateName } from '@/i18n'
import { ElMessage } from 'element-plus'
import * as api from '@/api/client'
import { dlog } from '@/utils/debugLog'

const { t, locale } = useI18n()
const appStore = useAppStore()
const schemaStore = useSchemaStore()
const paramsStore = useParamsStore()
const { generate, scheduleAutoGenerate } = useGenerate()

const debugOpen = ref<string[]>([])
const resetOpen = ref<string[]>([])
const jsonText = ref('')

// Computed options
const productOptions = computed(() =>
  schemaStore.products.map((p) => ({
    value: p.id,
    label: translateName(p.name, locale.value),
  })),
)

const componentOptions = computed(() => {
  const prod = schemaStore.currentProduct
  if (!prod) return []
  return prod.components.map((c) => ({
    value: c.id,
    label: translateName(c.name, locale.value) + (c.enabled ? '' : ' [!]'),
    disabled: !c.enabled,
  }))
})

const presetOptions = computed(() => {
  const comp = schemaStore.currentComponent
  if (!comp) return []
  return (comp.style_presets || []).map((s) => ({
    value: s.id,
    label: translateName(s.name, locale.value),
  }))
})

const presetDesc = computed(() => {
  const preset = schemaStore.currentPreset
  if (!preset) return ''
  const desc = preset.desc || ''
  return locale.value === 'zh' ? desc : translateName(desc, locale.value)
})

const isEnabled = computed(() => schemaStore.currentComponent?.enabled ?? false)

// Event handlers
async function onProductChange(val: string) {
  appStore.setProduct(val)
  const prod = schemaStore.currentProduct
  if (prod && prod.components.length > 0) {
    await onComponentChange(prod.components[0].id)
  }
}

async function onComponentChange(val: string) {
  dlog.switch(`═══ 切换组件: ${val} ═══`)
  appStore.setComponent(val)
  paramsStore.setCrossConstraints({})

  const comp = schemaStore.currentComponent
  if (comp && comp.style_presets && comp.style_presets.length > 0) {
    appStore.setPreset(comp.style_presets[0].id)
    paramsStore.setFromPreset(comp.style_presets[0].params)
    dlog.switch(`加载预设: ${comp.style_presets[0].id}`, comp.style_presets[0].params)
  }

  if (appStore.componentId) {
    const constraints = await api.fetchConstraints(appStore.componentId)
    dlog.switch(`获取约束: ${Object.keys(constraints).length} 条`, constraints)
    paramsStore.setCrossConstraints(constraints)
    paramsStore.applyCrossConstraints()
    dlog.switch('约束应用后的参数', JSON.parse(JSON.stringify(paramsStore.values)))
  }
}

function onPresetChange(val: string) {
  appStore.setPreset(val)
  const preset = schemaStore.currentPreset
  if (preset) {
    paramsStore.setFromPreset(preset.params)
  }
  if (appStore.autoGenerate) scheduleAutoGenerate()
}

// Generate
async function onGenerate() {
  await generate({ silent: false })
}

// Debug tools
function onExport() {
  jsonText.value = JSON.stringify(paramsStore.values, null, 2)
}

function onImport() {
  try {
    const obj = JSON.parse(jsonText.value || '{}')
    if (obj && typeof obj === 'object') {
      paramsStore.setAll(obj)
      if (appStore.autoGenerate) scheduleAutoGenerate()
    }
  } catch (e: any) {
    ElMessage.error(t('ui.jsonParseFail') + e.message)
  }
}

function onResetPreset() {
  const preset = schemaStore.currentPreset
  if (preset) {
    paramsStore.setFromPreset(preset.params)
  }
  if (appStore.autoGenerate) scheduleAutoGenerate()
}
</script>

<template>
  <div class="card left-panel">
    <div class="section-title">{{ t('ui.sectionSelect') }}</div>

    <div class="field-group">
      <label class="field-label">{{ t('ui.labelProduct') }}</label>
      <el-select
        :model-value="appStore.productId"
        @update:model-value="onProductChange"
        style="width: 100%"
      >
        <el-option
          v-for="opt in productOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
    </div>

    <div class="field-group">
      <label class="field-label">{{ t('ui.labelComponent') }}</label>
      <el-select
        :model-value="appStore.componentId"
        @update:model-value="onComponentChange"
        style="width: 100%"
      >
        <el-option
          v-for="opt in componentOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
          :disabled="opt.disabled"
        />
      </el-select>
    </div>

    <div class="field-group">
      <label class="field-label">{{ t('ui.labelPreset') }}</label>
      <el-select
        :model-value="appStore.presetId"
        @update:model-value="onPresetChange"
        style="width: 100%"
      >
        <el-option
          v-for="opt in presetOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <div class="preset-desc" v-if="presetDesc">{{ presetDesc }}</div>
    </div>

    <div class="divider" />

    <div class="section-title">{{ t('ui.sectionGenerate') }}</div>
    <el-button
      type="primary"
      @click="onGenerate"
      :disabled="!isEnabled || appStore.generating"
      :loading="appStore.generating"
      style="width: 100%; height: 42px; font-size: 14px"
    >
      {{ t('ui.btnGenerate') }}
    </el-button>
    <div
      class="gen-msg"
      :class="{ 'gen-msg--error': appStore.genMessageIsError, 'gen-msg--ok': !appStore.genMessageIsError && appStore.genMessage }"
    >
      {{ appStore.genMessage || (!isEnabled ? t('ui.notEnabled') : '') }}
    </div>

    <div class="options-row">
      <div class="option-item">
        <span class="option-label">{{ t('ui.labelAutoGen') }}</span>
        <el-switch v-model="appStore.autoGenerate" size="small" />
      </div>
    </div>

    <div class="field-group" style="margin-top: 8px">
      <label class="field-label">{{ t('ui.labelSearch') }}</label>
      <el-input
        v-model="appStore.filterText"
        :placeholder="t('ui.searchPlaceholder')"
        clearable
        size="small"
        :prefix-icon="''"
      />
    </div>

    <div class="divider" />

    <el-collapse v-model="debugOpen">
      <el-collapse-item :title="t('ui.debugTools')" name="debug">
        <div style="display: flex; gap: 8px; margin-bottom: 8px">
          <el-button size="small" @click="onExport">{{ t('ui.btnExport') }}</el-button>
          <el-button size="small" @click="onImport">{{ t('ui.btnImport') }}</el-button>
        </div>
        <el-input
          v-model="jsonText"
          type="textarea"
          :rows="4"
          placeholder='{"thread":{"profile":"rect"}}'
        />
      </el-collapse-item>
    </el-collapse>

    <el-collapse v-model="resetOpen" style="margin-top: 4px">
      <el-collapse-item :title="t('ui.resetPreset')" name="reset">
        <el-button size="small" @click="onResetPreset">
          {{ t('ui.btnReset') }}
        </el-button>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.left-panel {
  position: sticky;
  top: 16px;
}

.field-group {
  margin-bottom: 12px;
}

.field-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary, #475569);
  margin-bottom: 6px;
  letter-spacing: 0.2px;
}

.preset-desc {
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
  margin-top: 6px;
  line-height: 1.5;
}

.divider {
  height: 1px;
  background: var(--color-border, #e2e8f0);
  margin: 16px 0;
}

.gen-msg {
  font-size: 12px;
  margin-top: 8px;
  min-height: 18px;
  font-weight: 500;
}

.gen-msg--error {
  color: var(--color-error, #dc2626);
  font-weight: 700;
}

.gen-msg--ok {
  color: var(--color-success, #16a34a);
}

.options-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 12px;
}

.option-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.option-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary, #475569);
}
</style>

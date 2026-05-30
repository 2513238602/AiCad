<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useExoticCap } from '@/composables/useExoticCap'

const { t } = useI18n()
const {
  presets,
  loading,
  generating,
  error,
  lastResult,
  loadPresets,
  generate,
} = useExoticCap()

const selectedPresetId = ref<string | null>(null)
const targetOd = ref(24)
const useCustomHeight = ref(false)
const targetHeight = ref(30)

onMounted(() => {
  if (presets.value.length === 0) {
    loadPresets()
  }
})

function selectPreset(id: string) {
  selectedPresetId.value = id
  // 如果预设有默认高度，设为初始值
  const p = presets.value.find((x) => x.id === id)
  if (p?.default_height_mm) {
    targetHeight.value = p.default_height_mm
  }
}

const wallCheckColor = computed(() => {
  if (!lastResult.value?.wall_check) return ''
  return lastResult.value.wall_check.ok ? 'var(--color-success, #16a34a)' : 'var(--color-error, #dc2626)'
})

async function onGenerate() {
  if (!selectedPresetId.value) return
  await generate({
    presetId: selectedPresetId.value,
    targetOd: targetOd.value,
    targetHeight: useCustomHeight.value ? targetHeight.value : null,
  })
}
</script>

<template>
  <div class="exotic-panel">
    <div class="exotic-header">
      <h3 class="exotic-title">{{ t('exotic.title') }}</h3>
      <p class="exotic-desc">{{ t('exotic.description') }}</p>
    </div>

    <!-- 预设列表 -->
    <div v-if="loading" class="exotic-loading">{{ t('ui.loading') }}</div>
    <div v-else-if="presets.length === 0" class="exotic-empty">
      {{ t('exotic.noPresets') }}
    </div>
    <div v-else class="preset-grid">
      <div
        v-for="preset in presets"
        :key="preset.id"
        class="preset-card"
        :class="{ selected: selectedPresetId === preset.id }"
        @click="selectPreset(preset.id)"
      >
        <div class="preset-thumb">
          <img
            v-if="preset.thumbnail_url"
            :src="preset.thumbnail_url"
            :alt="preset.name"
          />
          <div v-else class="preset-thumb-placeholder">3D</div>
        </div>
        <div class="preset-name">{{ preset.name }}</div>
        <div class="preset-desc-text" v-if="preset.description">
          {{ preset.description }}
        </div>
      </div>
    </div>

    <!-- 参数控制 -->
    <div class="param-section" v-if="selectedPresetId">
      <div class="param-row">
        <label>{{ t('exotic.targetOd') }}</label>
        <el-slider
          v-model="targetOd"
          :min="16"
          :max="40"
          :step="0.5"
          show-input
          :show-input-controls="false"
          input-size="small"
        />
      </div>

      <div class="param-row">
        <el-checkbox v-model="useCustomHeight">
          {{ t('exotic.customHeight') }}
        </el-checkbox>
      </div>
      <div class="param-row" v-if="useCustomHeight">
        <label>{{ t('exotic.targetHeight') }}</label>
        <el-slider
          v-model="targetHeight"
          :min="15"
          :max="60"
          :step="0.5"
          show-input
          :show-input-controls="false"
          input-size="small"
        />
      </div>

      <!-- 生成按钮 -->
      <el-button
        type="primary"
        @click="onGenerate"
        :disabled="generating"
        :loading="generating"
        style="width: 100%; height: 42px; margin-top: 12px"
      >
        {{ generating ? t('exotic.generating') : t('exotic.btnGenerate') }}
      </el-button>

      <!-- 结果 -->
      <div v-if="error" class="result-msg result-error">{{ error }}</div>

      <div v-if="lastResult?.ok" class="result-msg result-ok">
        OK ({{ lastResult.time_sec }}s)
      </div>

      <div
        v-if="lastResult?.wall_check"
        class="wall-check"
        :style="{ color: wallCheckColor }"
      >
        {{ lastResult.wall_check.details }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.exotic-panel {
  padding: 4px 0;
}
.exotic-header {
  margin-bottom: 12px;
}
.exotic-title {
  font-size: 14px;
  font-weight: 700;
  margin: 0 0 4px;
}
.exotic-desc {
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
  margin: 0;
}
.exotic-loading,
.exotic-empty {
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
  padding: 16px 0;
  text-align: center;
}
.preset-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-bottom: 16px;
}
.preset-card {
  border: 2px solid var(--color-border, #e2e8f0);
  border-radius: 8px;
  padding: 8px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
  text-align: center;
}
.preset-card:hover {
  border-color: var(--el-color-primary-light-3, #79bbff);
}
.preset-card.selected {
  border-color: var(--el-color-primary, #409eff);
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}
.preset-thumb {
  width: 100%;
  aspect-ratio: 1;
  border-radius: 4px;
  overflow: hidden;
  background: var(--color-bg-muted, #f1f5f9);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 6px;
}
.preset-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.preset-thumb-placeholder {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-muted, #94a3b8);
}
.preset-name {
  font-size: 12px;
  font-weight: 600;
}
.preset-desc-text {
  font-size: 11px;
  color: var(--color-text-muted, #94a3b8);
  margin-top: 2px;
}
.param-section {
  margin-top: 8px;
}
.param-row {
  margin-bottom: 10px;
}
.param-row label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary, #475569);
  margin-bottom: 4px;
}
.result-msg {
  font-size: 12px;
  margin-top: 8px;
  font-weight: 500;
}
.result-error {
  color: var(--color-error, #dc2626);
}
.result-ok {
  color: var(--color-success, #16a34a);
}
.wall-check {
  font-size: 12px;
  margin-top: 4px;
  font-weight: 500;
}
</style>

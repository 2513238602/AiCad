<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWizardStore } from '@/stores/wizard'
import { useAppStore } from '@/stores/app'
import { useSchemaStore } from '@/stores/schema'
import { useParamsStore } from '@/stores/params'

const { t, locale } = useI18n()
const wizard = useWizardStore()
const appStore = useAppStore()
const schemaStore = useSchemaStore()
const paramsStore = useParamsStore()

const fallbackDescs: Record<string, Record<string, string>> = {
  zh: {
    cap: '外盖、内腔、防滑纹与密封配合',
    bottle: '瓶身、肩部、底部与口部结构',
    wiper: '刮片、孔口、凸环与密封结构',
    wand: '刷杆、刷头、气密环与帽盖配合',
  },
  en: {
    cap: 'Outer cap, cavity, grip texture, and sealing fit',
    bottle: 'Bottle body, shoulder, bottom, and neck finish',
    wiper: 'Wiper blade, orifice, flange, and seal geometry',
    wand: 'Stem, applicator, seal ring, and cap fit',
  },
}

function tName(name: string) {
  return t(`names.${name}`, name)
}

function componentDesc(comp: { id: string; desc?: string }) {
  if (comp.desc) return tName(comp.desc)
  const lang = locale.value === 'zh' ? 'zh' : 'en'
  return fallbackDescs[lang][comp.id] || comp.id
}

const components = computed(() => {
  return schemaStore.currentProduct?.components || []
})

function selectComponent(comp: { id: string; enabled: boolean; style_presets: any[] }) {
  if (!comp.enabled) return
  appStore.setComponent(comp.id)
  // Load first preset defaults
  if (comp.style_presets && comp.style_presets.length > 0) {
    appStore.setPreset(comp.style_presets[0].id)
    paramsStore.setFromPreset(comp.style_presets[0].params)
  }
  wizard.next()
}
</script>

<template>
  <div class="step-component">
    <h2 class="sc-title">{{ t('wizard.selectComponent') }}</h2>
    <div class="sc-cards">
      <div
        v-for="comp in components"
        :key="comp.id"
        class="sc-card"
        :class="{ 'sc-active': appStore.componentId === comp.id, 'sc-disabled': !comp.enabled }"
        @click="selectComponent(comp)"
      >
        <div class="sc-icon">{{ { cap: '\uD83E\uDDE2', bottle: '\uD83C\uDF76', wand: '\uD83E\uDE84', wiper: '\u2B55' }[comp.id] || '\uD83D\uDD27' }}</div>
        <div class="sc-name">{{ tName(comp.name) }}</div>
        <div class="sc-desc">{{ componentDesc(comp) }}</div>
        <el-tag
          v-if="!comp.enabled"
          size="small"
          type="info"
          effect="plain"
          style="margin-top: 6px"
        >
          {{ t('ui.notEnabled') }}
        </el-tag>
      </div>
    </div>
    <div class="sc-nav">
      <el-button @click="wizard.prev()">{{ t('wizard.btnBack') }}</el-button>
    </div>
  </div>
</template>

<style scoped>
.step-component {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
}

.sc-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 24px;
  color: #1e293b;
}

.sc-cards {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  justify-content: center;
  margin-bottom: 32px;
}

.sc-card {
  width: 160px;
  padding: 24px 16px;
  border: 2px solid #e2e8f0;
  border-radius: 14px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.sc-card:not(.sc-disabled):hover {
  border-color: #2563eb;
  box-shadow: 0 2px 16px rgba(37, 99, 235, 0.1);
  transform: translateY(-2px);
}

.sc-card.sc-active {
  border-color: #2563eb;
  background: #eff6ff;
}

.sc-card.sc-disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.sc-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.sc-name {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 4px;
}

.sc-desc {
  font-size: 11px;
  color: #64748b;
  line-height: 1.4;
}

.sc-nav {
  display: flex;
  gap: 12px;
}
</style>

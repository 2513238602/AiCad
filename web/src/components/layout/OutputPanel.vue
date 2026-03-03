<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import { useViewerStore } from '@/stores/viewer'
import type { QCCheck } from '@/api/types'
import DebugLogPanel from '@/components/output/DebugLogPanel.vue'

const { t } = useI18n()
const appStore = useAppStore()
const viewerStore = useViewerStore()

const activeTab = ref('3d')

const lastResponse = computed(() => appStore.lastResponse)

// Download links
const stepUrl = computed(() => lastResponse.value?.step_url)
const stlUrl = computed(() => lastResponse.value?.stl_url)
const svgUrl = computed(() => lastResponse.value?.svg_url)

// QC
const qcChecks = computed<QCCheck[]>(() => lastResponse.value?.qc?.checks || [])
const qcPassCount = computed(() => qcChecks.value.filter((c) => c.ok).length)
const qcFailCount = computed(() => qcChecks.value.filter((c) => !c.ok).length)

// Debug JSON
const debugJson = computed(() =>
  lastResponse.value ? JSON.stringify(lastResponse.value, null, 2) : '',
)

// 3D button info
const modelCountText = computed(() => {
  if (viewerStore.totalModels > 0) {
    const names = viewerStore.modelNames.map(
      (id) => t(`components.${id}`, id),
    )
    return `${names.length} ${t('ui.components')}: ${names.join(', ')}`
  }
  return t('ui.noModelYet')
})

const canOpen3d = computed(() => viewerStore.totalModels > 0)

function openViewer() {
  viewerStore.modalOpen = true
}
</script>

<template>
  <div class="card output-panel">
    <div class="section-title">{{ t('ui.sectionOutput') }}</div>

    <!-- Download links -->
    <div class="download-row" v-if="stepUrl || stlUrl || svgUrl">
      <a v-if="stepUrl" :href="stepUrl" target="_blank" class="download-link">
        <span class="download-icon">&#8615;</span> STEP
      </a>
      <a v-if="stlUrl" :href="stlUrl" target="_blank" class="download-link">
        <span class="download-icon">&#8615;</span> STL
      </a>
      <a v-if="svgUrl" :href="svgUrl" target="_blank" class="download-link">
        <span class="download-icon">&#8615;</span> SVG
      </a>
    </div>

    <!-- QC Results -->
    <div v-if="qcChecks.length > 0" class="qc-section">
      <div class="qc-header">
        <b>{{ t('ui.paramCheck') }}</b>
        <span v-if="qcFailCount > 0" class="qc-badge qc-badge--fail">
          {{ qcFailCount }} {{ t('ui.failedItems') }}
        </span>
        <span v-else-if="qcPassCount > 0" class="qc-badge qc-badge--pass">
          {{ qcPassCount }} {{ t('ui.allPassed') }}
        </span>
      </div>
      <div class="qc-list">
        <div v-for="c in qcChecks" :key="c.id" class="qc-item">
          <span v-if="c.ok" class="qc-ok">&check;</span>
          <span v-else class="qc-fail">&cross;</span>
          <span :class="c.ok ? 'pass' : (c.severity === 'hard' ? 'fail-hard' : 'fail-soft')">
            {{ c.ok ? c.id : `[${c.severity}] ${c.msg}` }}
          </span>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="tabs">
      <button
        v-for="tab in [{ key: '3d', label: t('ui.tab3d') }, { key: 'svg', label: t('ui.tabSvg') }, { key: 'log', label: t('ui.tabLog') }, { key: 'debug', label: t('ui.tabDebug') }]"
        :key="tab.key"
        :class="['tab-btn', { active: activeTab === tab.key }]"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 3D Tab -->
    <div v-show="activeTab === '3d'" class="tab-content">
      <button class="open-viewer-btn" :disabled="!canOpen3d" @click="openViewer">
        <span class="icon3d">&#9878;</span>
        <span>
          <span class="viewer-label">{{ t('ui.btnOpen3d') }}</span>
          <br />
          <span class="model-count">{{ modelCountText }}</span>
        </span>
      </button>
    </div>

    <!-- SVG Tab -->
    <div v-show="activeTab === 'svg'" class="tab-content">
      <iframe :src="svgUrl || 'about:blank'"></iframe>
    </div>

    <!-- Log Tab -->
    <div v-show="activeTab === 'log'" class="tab-content tab-content--log">
      <DebugLogPanel />
    </div>

    <!-- Debug Tab -->
    <div v-show="activeTab === 'debug'" class="tab-content">
      <pre>{{ debugJson }}</pre>
    </div>
  </div>
</template>

<style scoped>
.output-panel {
  margin-top: 20px;
}

.download-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.download-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  border: 1px solid var(--color-accent, #2563eb);
  border-radius: 8px;
  color: var(--color-accent, #2563eb);
  text-decoration: none;
  font-weight: 600;
  font-size: 13px;
  transition: all 0.15s;
}

.download-link:hover {
  background: var(--color-accent-light, #eff6ff);
}

.download-icon {
  font-size: 14px;
}

/* QC */
.qc-section {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--color-bg-hover, #f8fafc);
  border-radius: 8px;
}

.qc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}

.qc-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
}

.qc-badge--pass {
  background: var(--color-success-bg, #f0fdf4);
  color: var(--color-success, #16a34a);
}

.qc-badge--fail {
  background: var(--color-error-bg, #fef2f2);
  color: var(--color-error, #dc2626);
}

.qc-list {
  font-size: 12px;
  line-height: 1.8;
}

.qc-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.qc-ok { color: var(--color-success, #16a34a); }
.qc-fail { color: var(--color-error, #dc2626); }

/* Tabs */
.tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  border-bottom: 2px solid var(--color-border, #e2e8f0);
  padding-bottom: 0;
}

.tab-btn {
  background: transparent;
  border: none;
  padding: 8px 16px;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
  color: var(--color-text-muted, #94a3b8);
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.15s;
}

.tab-btn:hover {
  color: var(--color-text-secondary, #475569);
}

.tab-btn.active {
  color: var(--color-accent, #2563eb);
  border-bottom-color: var(--color-accent, #2563eb);
}

/* 3D Viewer button */
.open-viewer-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  width: 100%;
  padding: 28px;
  border: 2px dashed var(--color-border, #e2e8f0);
  border-radius: 12px;
  background: var(--color-bg-hover, #f8fafc);
  cursor: pointer;
  transition: all 0.2s;
}

.open-viewer-btn:hover:not(:disabled) {
  border-color: var(--color-accent, #2563eb);
  background: var(--color-accent-light, #eff6ff);
}

.open-viewer-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.icon3d {
  font-size: 32px;
  color: var(--color-accent, #2563eb);
}

.viewer-label {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary, #1e293b);
}

.model-count {
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
  font-weight: 400;
}

.tab-content--log {
  min-height: 360px;
}
</style>

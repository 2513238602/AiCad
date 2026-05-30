<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWizardStore, WizardStep } from '@/stores/wizard'
import { useAppStore } from '@/stores/app'
import { useViewerStore } from '@/stores/viewer'
import { useGenerate } from '@/composables/useGenerate'

const { t } = useI18n()
const wizard = useWizardStore()
const appStore = useAppStore()
const viewerStore = useViewerStore()
const { generate } = useGenerate()
const generated = ref(false)

const canOpen3d = computed(() => viewerStore.totalModels > 0)

function openViewer() {
  viewerStore.modalOpen = true
}

onMounted(async () => {
  // Auto-generate on entering this step
  if (!generated.value) {
    generated.value = true
    await generate()
  }
})

async function onRegenerate() {
  await generate()
}

function onEditParams() {
  wizard.goTo(WizardStep.CoreParams)
}

function onEditFineTune() {
  wizard.goTo(WizardStep.FineTune)
}

function onNextComponent() {
  wizard.goTo(WizardStep.Component)
}
</script>

<template>
  <div class="step-generate">
    <h2 class="sg-title">{{ t('wizard.generateTitle') }}</h2>

    <!-- Status -->
    <div class="sg-status" :class="{ 'sg-err': appStore.genMessageIsError }">
      <template v-if="appStore.generating">
        <el-icon class="is-loading" style="margin-right: 6px"><i class="el-icon-loading" /></el-icon>
        {{ t('ui.generating') }}
      </template>
      <template v-else-if="appStore.lastResponse?.ok">
        <span class="sg-ok-icon">&#10003;</span>
        {{ t('ui.ok') }}
        <span v-if="appStore.lastResponse?.time_sec" class="sg-time">
          {{ t('ui.timeSec') }}: {{ appStore.lastResponse.time_sec }}s
        </span>
      </template>
      <template v-else-if="appStore.genMessage">
        {{ appStore.genMessage }}
      </template>
    </div>

    <!-- QC Results -->
    <div v-if="appStore.lastResponse?.qc" class="sg-qc">
      <div class="sg-qc-title">{{ t('ui.paramCheck') }}</div>
      <div
        v-for="check in (appStore.lastResponse.qc as any).checks || []"
        :key="check.id"
        class="sg-qc-item"
        :class="{ 'sg-qc-fail': !check.ok }"
      >
        <span>{{ check.ok ? '&#10003;' : '&#10007;' }}</span>
        <span>{{ check.msg }}</span>
      </div>
    </div>

    <!-- 3D Preview button -->
    <div v-if="appStore.lastResponse?.ok" class="sg-viewer">
      <el-button
        type="primary"
        size="large"
        :disabled="!canOpen3d"
        @click="openViewer"
        style="width: 100%"
      >
        <span style="margin-right: 6px; font-size: 18px">&#9878;</span>
        {{ t('ui.btnOpen3d') }}
        <span v-if="canOpen3d" style="margin-left: 8px; opacity: 0.7; font-size: 12px">
          ({{ viewerStore.totalModels }} {{ t('ui.components') }})
        </span>
      </el-button>
    </div>

    <!-- Download links -->
    <div v-if="appStore.lastResponse?.ok" class="sg-downloads">
      <a v-if="appStore.lastResponse.step_url" :href="appStore.lastResponse.step_url" class="sg-dl-btn">
        {{ t('ui.downloadStep') }}
      </a>
      <a v-if="appStore.lastResponse.stl_url" :href="appStore.lastResponse.stl_url" class="sg-dl-btn">
        {{ t('ui.downloadStl') }}
      </a>
      <a v-if="appStore.lastResponse.svg_url" :href="appStore.lastResponse.svg_url" class="sg-dl-btn">
        {{ t('ui.downloadSvg') }}
      </a>
    </div>

    <!-- Action buttons -->
    <div class="sg-actions">
      <el-button @click="onRegenerate" :loading="appStore.generating">
        {{ t('wizard.regenerate') }}
      </el-button>
      <el-button @click="onEditParams">
        {{ t('wizard.editParams') }}
      </el-button>
      <el-button @click="onEditFineTune">
        {{ t('wizard.editFineTune') }}
      </el-button>
      <el-button type="primary" @click="onNextComponent">
        {{ t('wizard.nextComponent') }}
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.step-generate {
  max-width: 560px;
  margin: 0 auto;
  padding: 32px 20px;
}

.sg-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 16px;
  color: #1e293b;
}

.sg-status {
  padding: 12px 16px;
  border-radius: 10px;
  background: #f0fdf4;
  color: #166534;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
}

.sg-status.sg-err {
  background: #fef2f2;
  color: #991b1b;
}

.sg-ok-icon {
  color: #10b981;
  font-size: 18px;
  margin-right: 8px;
}

.sg-time {
  margin-left: auto;
  font-weight: 400;
  font-size: 12px;
  color: #64748b;
}

.sg-qc {
  margin-bottom: 16px;
  padding: 12px;
  background: #fafbfc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.sg-qc-title {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 8px;
}

.sg-qc-item {
  font-size: 12px;
  color: #10b981;
  display: flex;
  gap: 6px;
  padding: 2px 0;
}

.sg-qc-item.sg-qc-fail {
  color: #ef4444;
}

.sg-viewer {
  margin-bottom: 16px;
}

.sg-downloads {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}

.sg-dl-btn {
  padding: 8px 16px;
  background: #2563eb;
  color: white;
  border-radius: 8px;
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
  transition: background 0.15s;
}

.sg-dl-btn:hover {
  background: #1d4ed8;
}

.sg-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>

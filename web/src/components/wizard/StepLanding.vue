<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useWizardStore, WizardStep } from '@/stores/wizard'

const { t } = useI18n()
const wizard = useWizardStore()

function onManual() {
  wizard.next()
}

function onImageImport() {
  wizard.goTo(WizardStep.ImageImport)
}
</script>

<template>
  <div class="step-landing">
    <h2 class="sl-title">{{ t('wizard.landingTitle') }}</h2>
    <p class="sl-desc">{{ t('wizard.landingDesc') }}</p>
    <div class="sl-cards">
      <div class="sl-card sl-primary" @click="onManual">
        <div class="sl-icon">&#9998;</div>
        <div class="sl-card-title">{{ t('wizard.manualDesign') }}</div>
        <div class="sl-card-desc">{{ t('wizard.manualDesignDesc') }}</div>
      </div>
      <div class="sl-card sl-secondary" @click="onImageImport">
        <div class="sl-icon">&#128247;</div>
        <div class="sl-card-title">{{ t('wizard.imageImport') }}</div>
        <div class="sl-card-desc">{{ t('wizard.imageImportDesc') }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.step-landing {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  padding: 40px 20px;
}

.sl-title {
  font-size: 28px;
  font-weight: 800;
  margin: 0 0 8px;
  background: linear-gradient(135deg, #1e293b 0%, #2563eb 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.sl-desc {
  color: #64748b;
  font-size: 14px;
  margin: 0 0 32px;
}

.sl-cards {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  justify-content: center;
}

.sl-card {
  width: 240px;
  padding: 32px 24px;
  border: 2px solid #e2e8f0;
  border-radius: 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.sl-card.sl-primary:hover {
  border-color: #2563eb;
  box-shadow: 0 4px 24px rgba(37, 99, 235, 0.12);
  transform: translateY(-2px);
}

.sl-card.sl-secondary:hover {
  border-color: #10b981;
  box-shadow: 0 4px 24px rgba(16, 185, 129, 0.12);
  transform: translateY(-2px);
}

.sl-icon {
  font-size: 36px;
  margin-bottom: 12px;
}

.sl-card-title {
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 6px;
}

.sl-card-desc {
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

.sl-tag {
  margin-top: 10px;
}
</style>

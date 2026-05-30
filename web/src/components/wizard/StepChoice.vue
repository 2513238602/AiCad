<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useWizardStore, WizardStep } from '@/stores/wizard'

const { t } = useI18n()
const wizard = useWizardStore()

function onDefault() {
  // Skip fine-tune, go directly to generate
  wizard.goTo(WizardStep.Generate)
}

function onFineTune() {
  wizard.next()
}
</script>

<template>
  <div class="step-choice">
    <h2 class="sch-title">{{ t('wizard.choiceTitle') }}</h2>
    <p class="sch-desc">{{ t('wizard.choiceDesc') }}</p>
    <div class="sch-cards">
      <div class="sch-card sch-primary" @click="onDefault">
        <div class="sch-icon">&#9889;</div>
        <div class="sch-card-title">{{ t('wizard.defaultGenerate') }}</div>
        <div class="sch-card-desc">{{ t('wizard.defaultGenerateDesc') }}</div>
      </div>
      <div class="sch-card" @click="onFineTune">
        <div class="sch-icon">&#9881;</div>
        <div class="sch-card-title">{{ t('wizard.fineTune') }}</div>
        <div class="sch-card-desc">{{ t('wizard.fineTuneDesc') }}</div>
      </div>
    </div>
    <div class="sch-nav">
      <el-button @click="wizard.prev()">{{ t('wizard.btnBack') }}</el-button>
    </div>
  </div>
</template>

<style scoped>
.step-choice {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
}

.sch-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 6px;
  color: #1e293b;
}

.sch-desc {
  color: #64748b;
  font-size: 13px;
  margin: 0 0 32px;
}

.sch-cards {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  justify-content: center;
  margin-bottom: 32px;
}

.sch-card {
  width: 220px;
  padding: 32px 24px;
  border: 2px solid #e2e8f0;
  border-radius: 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.sch-card:hover {
  border-color: #2563eb;
  box-shadow: 0 4px 24px rgba(37, 99, 235, 0.12);
  transform: translateY(-2px);
}

.sch-card.sch-primary {
  border-color: #93c5fd;
  background: #f0f7ff;
}

.sch-icon {
  font-size: 32px;
  margin-bottom: 12px;
}

.sch-card-title {
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 6px;
}

.sch-card-desc {
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

.sch-nav {
  display: flex;
  gap: 12px;
}
</style>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useWizardStore, STEPS, WizardStep } from '@/stores/wizard'

const { t } = useI18n()
const wizard = useWizardStore()

function onClickStep(step: WizardStep) {
  // Only allow going back to previously visited steps
  if (step <= wizard.highestStep) {
    wizard.goTo(step)
  }
}
</script>

<template>
  <div class="wizard-nav">
    <div
      v-for="meta in STEPS"
      :key="meta.step"
      class="wn-step"
      :class="{
        'wn-active': wizard.currentStep === meta.step,
        'wn-done': meta.step < wizard.currentStep,
        'wn-reachable': meta.step <= wizard.highestStep && meta.step !== wizard.currentStep,
        'wn-future': meta.step > wizard.highestStep,
      }"
      @click="onClickStep(meta.step)"
    >
      <div class="wn-dot">
        <span v-if="meta.step < wizard.currentStep" class="wn-check">&#10003;</span>
        <span v-else>{{ meta.step + 1 }}</span>
      </div>
      <span class="wn-label">{{ t(meta.labelKey) }}</span>
    </div>
  </div>
</template>

<style scoped>
.wizard-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 0;
  overflow-x: auto;
}

.wn-step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  transition: all 0.2s;
  cursor: default;
  color: #94a3b8;
}

.wn-step.wn-reachable {
  cursor: pointer;
}
.wn-step.wn-reachable:hover {
  background: #f1f5f9;
}

.wn-step.wn-active {
  background: #eff6ff;
  color: #2563eb;
  font-weight: 600;
}

.wn-step.wn-done {
  color: #10b981;
  cursor: pointer;
}
.wn-step.wn-done:hover {
  background: #ecfdf5;
}

.wn-dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  background: #e2e8f0;
  color: #64748b;
  flex-shrink: 0;
  transition: all 0.2s;
}

.wn-active .wn-dot {
  background: #2563eb;
  color: white;
}

.wn-done .wn-dot {
  background: #10b981;
  color: white;
}

.wn-check {
  font-size: 12px;
}

.wn-label {
  display: none;
}

/* Show labels on wider screens */
@media (min-width: 800px) {
  .wn-label {
    display: inline;
  }
}
</style>

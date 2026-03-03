<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const appStore = useAppStore()
const visible = ref(false)

// Show popup when generate fails
watch(
  () => appStore.lastResponse,
  (res) => {
    if (res && res.ok === false) {
      visible.value = true
      setTimeout(() => {
        visible.value = false
      }, 1000)
    }
  },
)
</script>

<template>
  <Teleport to="body">
    <div class="fail-popup" :class="{ show: visible }">
      {{ t('ui.genFailed') }}
    </div>
  </Teleport>
</template>

<style scoped>
.fail-popup {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: var(--color-error);
  color: #fff;
  padding: 24px 48px;
  border-radius: 12px;
  font-size: 18px;
  font-weight: 700;
  z-index: 9999;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
}
.fail-popup.show {
  opacity: 1;
}
</style>

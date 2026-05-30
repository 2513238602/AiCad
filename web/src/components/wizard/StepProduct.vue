<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useWizardStore } from '@/stores/wizard'
import { useAppStore } from '@/stores/app'
import { useSchemaStore } from '@/stores/schema'

const { t } = useI18n()
const wizard = useWizardStore()
const appStore = useAppStore()
const schemaStore = useSchemaStore()

function tName(name: string) {
  return t(`names.${name}`, name)
}

function selectProduct(id: string) {
  appStore.setProduct(id)
  wizard.next()
}
</script>

<template>
  <div class="step-product">
    <h2 class="sp-title">{{ t('wizard.selectProduct') }}</h2>
    <div class="sp-cards">
      <div
        v-for="prod in schemaStore.products"
        :key="prod.id"
        class="sp-card"
        :class="{ 'sp-active': appStore.productId === prod.id, 'sp-disabled': prod.id !== 'lip_gloss' }"
        @click="prod.id === 'lip_gloss' && selectProduct(prod.id)"
      >
        <div class="sp-card-name">{{ tName(prod.name) }}</div>
        <div class="sp-card-desc">
          {{ prod.components.length }} {{ t('wizard.componentCount') }}
        </div>
        <el-tag
          v-if="prod.id !== 'lip_gloss'"
          size="small"
          type="info"
          effect="plain"
          style="margin-top: 8px"
        >
          {{ t('wizard.comingSoon') }}
        </el-tag>
      </div>
    </div>
    <div class="sp-nav">
      <el-button @click="wizard.prev()">{{ t('wizard.btnBack') }}</el-button>
    </div>
  </div>
</template>

<style scoped>
.step-product {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
}

.sp-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 24px;
  color: #1e293b;
}

.sp-cards {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  justify-content: center;
  margin-bottom: 32px;
}

.sp-card {
  width: 200px;
  padding: 24px 20px;
  border: 2px solid #e2e8f0;
  border-radius: 14px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.sp-card:not(.sp-disabled):hover {
  border-color: #2563eb;
  box-shadow: 0 2px 16px rgba(37, 99, 235, 0.1);
}

.sp-card.sp-active {
  border-color: #2563eb;
  background: #eff6ff;
}

.sp-card.sp-disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.sp-card-name {
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 4px;
}

.sp-card-desc {
  font-size: 12px;
  color: #64748b;
}

.sp-nav {
  display: flex;
  gap: 12px;
}
</style>

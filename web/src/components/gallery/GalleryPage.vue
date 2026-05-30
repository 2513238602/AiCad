<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWizardStore, WizardStep } from '@/stores/wizard'
import { useViewerStore } from '@/stores/viewer'
import { fetchGallery, generateGalleryItem, fetchGalleryPrebuilt } from '@/api/client'
import type { GalleryItem, GalleryGenerateResponse, GalleryVariant } from '@/api/types'

const { t } = useI18n()
const wizard = useWizardStore()
const viewer = useViewerStore()

const items = ref<GalleryItem[]>([])
const loading = ref(true)
const generating = ref<string | null>(null)
const error = ref('')
const expandedGroup = ref<string | null>(null)
const loadingVariant = ref<string | null>(null)

onMounted(async () => {
  try {
    const data = await fetchGallery()
    items.value = data.items
  } catch (e: any) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
})

async function loadPrebuilt(catId: string, prebuilt?: boolean) {
  generating.value = catId
  try {
    let res: GalleryGenerateResponse
    if (prebuilt) {
      res = await fetchGalleryPrebuilt(catId)
    } else {
      res = await generateGalleryItem(catId)
    }
    if (!res.ok) {
      alert(res.error || 'Generation failed')
      return
    }

    if (viewer.modalOpen) {
      viewer.modalOpen = false
      await nextTick()
    }
    viewer.clearAll()
    viewer.sessionSource = 'gallery'
    viewer.renderMode = 'simple'

    for (const cid of ['bottle', 'cap', 'wand', 'wiper']) {
      const r = res.results?.[cid]
      if (r?.ok && r.stl_url) {
        viewer.storePendingSTL(cid, r.stl_url, r.qc?.params || {})
      }
    }
    if (res.assembly?.positions) {
      viewer.setAssemblyPositions(res.assembly.positions)
    }

    await nextTick()
    viewer.modalOpen = true
  } catch (e: any) {
    alert(String(e))
  } finally {
    generating.value = null
    loadingVariant.value = null
  }
}

function onCardClick(item: GalleryItem) {
  if (generating.value) return
  if (item.variants && item.variants.length > 1) {
    expandedGroup.value = expandedGroup.value === item.cat_id ? null : item.cat_id
    return
  }
  loadPrebuilt(item.cat_id, item.prebuilt)
}

function onVariantClick(variant: GalleryVariant) {
  if (generating.value) return
  loadingVariant.value = variant.cat_id
  loadPrebuilt(variant.cat_id, variant.prebuilt)
}

function goBack() {
  wizard.setMode('wizard')
  wizard.goTo(WizardStep.Landing)
}
</script>

<template>
  <div class="gallery-page">
    <div class="gallery-header">
      <button class="back-btn" @click="goBack">&larr; {{ t('gallery.back') }}</button>
      <div class="header-center">
        <h2 class="gallery-title">{{ t('gallery.title') }}</h2>
        <span class="gallery-subtitle">{{ items.length }} {{ t('gallery.styles') }} &middot; {{ t('gallery.clickHint') }}</span>
      </div>
    </div>

    <div v-if="loading" class="gallery-loading">{{ t('ui.loading') }}</div>
    <div v-else-if="error" class="gallery-error">{{ error }}</div>

    <div v-else class="gallery-grid">
      <div
        v-for="item in items"
        :key="item.cat_id"
        class="gallery-card"
        :class="{
          'is-generating': generating === item.cat_id,
          'is-disabled': generating && generating !== item.cat_id && loadingVariant === null,
          'is-expanded': item.variants && expandedGroup === item.cat_id,
          'has-variants': item.variants && item.variants.length > 1,
        }"
        @click="onCardClick(item)"
      >
        <div class="card-image">
          <img
            v-if="item.thumbnail"
            :src="item.thumbnail"
            :alt="item.desc"
            loading="lazy"
          />
          <div v-else class="no-image">?</div>
          <div v-if="generating === item.cat_id && !loadingVariant" class="card-overlay">
            <div class="spinner" />
            <span>{{ t('gallery.generating') }}</span>
          </div>
          <div v-if="item.variants && item.variants.length > 1" class="variant-badge">
            {{ item.variants.length }} {{ t('gallery.versions') }}
          </div>
        </div>
        <div class="card-info">
          <span class="card-id">{{ item.cat_id }}</span>
          <span class="card-desc">{{ item.desc }}</span>
        </div>
        <!-- 版本选择器 -->
        <div
          v-if="item.variants && item.variants.length > 1 && expandedGroup === item.cat_id"
          class="variant-picker"
          @click.stop
        >
          <div class="variant-hint">{{ t('gallery.variantHint') }}</div>
          <button
            v-for="v in item.variants"
            :key="v.cat_id"
            class="variant-btn"
            :class="{ 'is-loading': loadingVariant === v.cat_id, 'no-prebuilt': !v.prebuilt }"
            :disabled="!!generating"
            @click="onVariantClick(v)"
          >
            <span class="variant-label">{{ v.label }}</span>
            <span class="variant-desc">{{ v.desc }}</span>
            <span v-if="loadingVariant === v.cat_id" class="spinner-sm" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gallery-page {
  padding: 8px 0;
}

.gallery-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.back-btn {
  background: var(--color-bg-card, #fff);
  color: var(--color-text-primary, #1e293b);
  border: 1px solid var(--color-border, #e2e8f0);
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
  transition: all 0.15s;
  white-space: nowrap;
}

.back-btn:hover {
  background: var(--color-bg-hover, #f8fafc);
  border-color: var(--color-accent, #2563eb);
  color: var(--color-accent, #2563eb);
}

.header-center {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.gallery-title {
  margin: 0;
  font-size: 20px;
  font-weight: 800;
  color: var(--color-text-primary, #1e293b);
}

.gallery-subtitle {
  font-size: 13px;
  color: var(--color-text-muted, #94a3b8);
}

.gallery-loading,
.gallery-error {
  text-align: center;
  padding: 60px 0;
  color: var(--color-text-muted, #94a3b8);
  font-size: 15px;
}

.gallery-error {
  color: #ef4444;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

@media (max-width: 1024px) {
  .gallery-grid { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 640px) {
  .gallery-grid { grid-template-columns: repeat(2, 1fr); }
}

.gallery-card {
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--color-bg-card, #fff);
}

.gallery-card:hover:not(.is-disabled) {
  border-color: var(--color-accent, #2563eb);
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.12);
  transform: translateY(-2px);
}

.gallery-card.is-expanded {
  border-color: var(--color-accent, #2563eb);
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.12);
}

.gallery-card.is-generating {
  border-color: #10b981;
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
}

.gallery-card.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.card-image {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  background: #f8fafc;
}

.card-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}

.gallery-card:hover:not(.is-disabled) .card-image img {
  transform: scale(1.05);
}

.no-image {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  color: #cbd5e1;
}

.card-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
}

.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.variant-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: var(--color-accent, #2563eb);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 10px;
  letter-spacing: 0.3px;
}

.card-info {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.card-id {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-accent, #2563eb);
  letter-spacing: 0.3px;
  text-transform: uppercase;
}

.card-desc {
  font-size: 13px;
  color: var(--color-text-primary, #1e293b);
  font-weight: 500;
}

/* 版本选择器 */
.variant-picker {
  border-top: 1px solid var(--color-border, #e2e8f0);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  animation: slideDown 0.2s ease-out;
}

@keyframes slideDown {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 300px; }
}

.variant-hint {
  font-size: 11px;
  color: var(--color-text-muted, #94a3b8);
  padding: 0 4px;
  font-weight: 600;
}

.variant-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 8px;
  background: var(--color-bg-card, #fff);
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}

.variant-btn:hover:not(:disabled) {
  border-color: var(--color-accent, #2563eb);
  background: rgba(37, 99, 235, 0.04);
}

.variant-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.variant-btn.is-loading {
  border-color: #10b981;
  background: rgba(16, 185, 129, 0.06);
}

.variant-btn.no-prebuilt {
  border-style: dashed;
}

.variant-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-text-primary, #1e293b);
  white-space: nowrap;
}

.variant-desc {
  font-size: 11px;
  color: var(--color-text-muted, #94a3b8);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(16, 185, 129, 0.3);
  border-top-color: #10b981;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}
</style>

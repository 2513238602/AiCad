<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWizardStore } from '@/stores/wizard'
import * as api from '@/api/client'

const { t, locale } = useI18n()
const wizard = useWizardStore()
const rebuilding = ref(false)

function toggleLanguage() {
  locale.value = locale.value === 'zh' ? 'en' : 'zh'
  document.documentElement.lang = locale.value === 'zh' ? 'zh-CN' : 'en'
  document.title = t('ui.title')
}

async function onRebuild() {
  rebuilding.value = true
  try {
    const res = await api.rebuild()
    if (res.ok) {
      // 强制清除缓存后刷新：添加时间戳参数绕过浏览器缓存
      window.location.href = '/?_t=' + Date.now()
    } else {
      // 显示详细错误信息，帮助诊断问题
      const r = res as Record<string, any>
      const detail = r.stderr ? `\n\nstderr: ${String(r.stderr).slice(-200)}` : ''
      alert(t('ui.rebuildFail') + (res.error || '') + detail)
      rebuilding.value = false
    }
  } catch (e: any) {
    alert(t('ui.rebuildFail') + String(e))
    rebuilding.value = false
  }
}
</script>

<template>
  <header class="app-header">
    <div class="header-left">
      <h1 class="header-title">
        {{ t('ui.title') }}
      </h1>
      <span class="header-pill">{{ t('ui.subtitle') }}</span>
    </div>
    <div class="header-right">
      <span class="header-hint">{{ t('ui.outputFormat') }}</span>
      <button
        class="mode-nav-btn"
        :class="{ active: wizard.appMode === 'wizard' }"
        @click="wizard.setMode('wizard')"
      >
        {{ t('ui.wizardMode') }}
      </button>
      <button
        class="mode-nav-btn"
        :class="{ active: wizard.appMode === 'classic' }"
        @click="wizard.setMode('classic')"
      >
        {{ t('ui.classicMode') }}
      </button>
      <button
        class="mode-nav-btn"
        :class="{ active: wizard.appMode === 'gallery' }"
        @click="wizard.setMode('gallery')"
      >
        {{ t('gallery.btnGallery') }}
      </button>
      <button
        class="mode-nav-btn showroom"
        :class="{ active: wizard.appMode === 'showroom' }"
        @click="wizard.setMode('showroom')"
      >
        {{ t('showroom.btnShowroom') }}
      </button>
      <button class="rebuild-btn" @click="onRebuild" :disabled="rebuilding">
        {{ rebuilding ? t('ui.rebuilding') : t('ui.btnRebuild') }}
      </button>
      <button class="lang-btn" @click="toggleLanguage">
        {{ t('ui.langToggle') }}
      </button>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px 0 12px;
  border-bottom: 1px solid var(--color-border, #e2e8f0);
  margin-bottom: 4px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-title {
  font-size: 22px;
  font-weight: 800;
  margin: 0;
  letter-spacing: -0.5px;
  color: var(--color-text-primary, #1e293b);
  background: linear-gradient(135deg, #1e293b 0%, #2563eb 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.header-pill {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 999px;
  background: var(--color-accent-light, #eff6ff);
  color: var(--color-accent, #2563eb);
  border: 1px solid var(--color-accent-50, #dbeafe);
  letter-spacing: 0.3px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-hint {
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
  font-weight: 500;
}

.lang-btn {
  background: var(--color-bg-card, #fff);
  color: var(--color-text-primary, #1e293b);
  border: 1px solid var(--color-border, #e2e8f0);
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
  transition: all 0.15s;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
}

.lang-btn:hover {
  background: var(--color-bg-hover, #f8fafc);
  border-color: var(--color-accent, #2563eb);
  color: var(--color-accent, #2563eb);
}

.mode-nav-btn {
  background: var(--color-bg-card, #fff);
  color: var(--color-text-secondary, #475569);
  border: 1px solid var(--color-border, #e2e8f0);
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
  transition: all 0.15s;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
}

.mode-nav-btn:hover,
.mode-nav-btn.active {
  background: #eef2ff;
  border-color: #4f46e5;
  color: #4f46e5;
}

.mode-nav-btn.showroom.active,
.mode-nav-btn.showroom:hover {
  background: #ecfeff;
  border-color: #0891b2;
  color: #0e7490;
}

.rebuild-btn {
  background: var(--color-bg-card, #fff);
  color: var(--color-warning, #d97706);
  border: 1px solid var(--color-warning, #d97706);
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
  transition: all 0.15s;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
}

.rebuild-btn:hover:not(:disabled) {
  background: #fffbeb;
  border-color: #b45309;
  color: #b45309;
}

.rebuild-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}
</style>

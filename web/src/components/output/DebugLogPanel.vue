<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { dlog, type LogEntry } from '@/utils/debugLog'

const entries = ref<LogEntry[]>([])
const logContainer = ref<HTMLElement | null>(null)
const autoScroll = ref(true)
let unsubscribe: (() => void) | null = null

function refresh() {
  entries.value = [...dlog.getAll()]
  if (autoScroll.value) {
    nextTick(() => {
      if (logContainer.value) {
        logContainer.value.scrollTop = logContainer.value.scrollHeight
      }
    })
  }
}

onMounted(() => {
  refresh()
  unsubscribe = dlog.subscribe(refresh)
})

onUnmounted(() => {
  unsubscribe?.()
})

function onClear() {
  dlog.clear()
  entries.value = []
}

function onExport() {
  const text = dlog.exportText()
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `aicad-debug-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.log`
  a.click()
  URL.revokeObjectURL(url)
}

function categoryColor(cat: string): string {
  const map: Record<string, string> = {
    constraint: '#e67e22',
    param: '#2980b9',
    generate: '#27ae60',
    switch: '#8e44ad',
    derived: '#16a085',
    warning: '#c0392b',
  }
  return map[cat] || '#666'
}

function categoryLabel(cat: string): string {
  const map: Record<string, string> = {
    constraint: '约束',
    param: '参数',
    generate: '生成',
    switch: '切换',
    derived: '派生',
    warning: '警告',
  }
  return map[cat] || cat
}
</script>

<template>
  <div class="debug-log-panel">
    <div class="log-toolbar">
      <span class="log-count">{{ entries.length }} 条日志</span>
      <label class="log-option">
        <input type="checkbox" v-model="autoScroll" />
        自动滚动
      </label>
      <button class="log-btn" @click="onExport" title="导出日志文件">导出</button>
      <button class="log-btn log-btn--danger" @click="onClear" title="清空日志">清空</button>
    </div>
    <div class="log-entries" ref="logContainer">
      <div
        v-for="(entry, i) in entries"
        :key="i"
        class="log-entry"
        :class="{ 'log-entry--warning': entry.category === 'warning' }"
      >
        <span class="log-time">{{ entry.time }}</span>
        <span
          class="log-cat"
          :style="{ background: categoryColor(entry.category) }"
        >{{ categoryLabel(entry.category) }}</span>
        <span class="log-msg">{{ entry.message }}</span>
        <details v-if="entry.data" class="log-data-details">
          <summary>data</summary>
          <pre class="log-data">{{ JSON.stringify(entry.data, null, 2) }}</pre>
        </details>
      </div>
      <div v-if="entries.length === 0" class="log-empty">
        暂无日志。切换组件、修改参数或生成时会自动记录。
      </div>
    </div>
  </div>
</template>

<style scoped>
.debug-log-panel {
  display: flex;
  flex-direction: column;
  height: 360px;
}

.log-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--color-border, #e2e8f0);
  font-size: 12px;
}

.log-count {
  color: var(--color-text-muted, #94a3b8);
  font-weight: 500;
}

.log-option {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--color-text-secondary, #475569);
  cursor: pointer;
  margin-left: auto;
}

.log-btn {
  padding: 2px 10px;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 4px;
  background: white;
  font-size: 11px;
  cursor: pointer;
  color: var(--color-text-secondary, #475569);
}

.log-btn:hover {
  background: var(--color-bg-hover, #f8fafc);
}

.log-btn--danger {
  color: var(--color-error, #dc2626);
  border-color: var(--color-error, #dc2626);
}

.log-entries {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.6;
}

.log-entry {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 2px 4px;
  border-radius: 3px;
}

.log-entry:hover {
  background: var(--color-bg-hover, #f8fafc);
}

.log-entry--warning {
  background: #fef2f2;
}

.log-entry--warning:hover {
  background: #fee2e2;
}

.log-time {
  color: var(--color-text-muted, #94a3b8);
  white-space: nowrap;
  flex-shrink: 0;
}

.log-cat {
  display: inline-block;
  padding: 0 5px;
  border-radius: 3px;
  color: white;
  font-size: 10px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  line-height: 18px;
}

.log-msg {
  color: var(--color-text-primary, #1e293b);
  word-break: break-all;
}

.log-data-details {
  margin-left: 4px;
  flex-shrink: 0;
}

.log-data-details summary {
  cursor: pointer;
  color: var(--color-accent, #2563eb);
  font-size: 10px;
}

.log-data {
  margin: 4px 0;
  padding: 6px;
  background: var(--color-bg-secondary, #f1f5f9);
  border-radius: 4px;
  font-size: 10px;
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.log-empty {
  padding: 20px;
  text-align: center;
  color: var(--color-text-muted, #94a3b8);
}
</style>

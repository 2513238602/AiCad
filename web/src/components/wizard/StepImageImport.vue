<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWizardStore } from '@/stores/wizard'
import { useViewerStore } from '@/stores/viewer'
import type { VlmProgressEvent } from '@/api/types'

const { t } = useI18n()
const wizard = useWizardStore()
const viewerStore = useViewerStore()

// 图片预览 URL
const imagePreviewUrl = ref('')

// ── 图片上传处理 ──
function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input?.files?.[0]
  if (!file) return
  if (file.size > 10 * 1024 * 1024) {
    alert('图片不能超过 10MB')
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    const dataUrl = reader.result as string
    imagePreviewUrl.value = dataUrl
    // 提取 base64 部分（去掉 data:image/...;base64, 前缀）
    const idx = dataUrl.indexOf(',')
    wizard.vlmImageB64 = idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl
  }
  reader.readAsDataURL(file)
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  const file = e.dataTransfer?.files?.[0]
  if (!file) return
  const fakeEvent = { target: { files: [file] } } as unknown as Event
  onFileChange(fakeEvent)
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
}

// ── 进度条 + 计时器 ──
const progressPct = ref(0)
const elapsed = ref(0)
let timerHandle: ReturnType<typeof setInterval> | null = null

function startTimer() {
  elapsed.value = 0
  timerHandle = setInterval(() => { elapsed.value++ }, 1000)
}
function stopTimer() {
  if (timerHandle) { clearInterval(timerHandle); timerHandle = null }
}
onUnmounted(stopTimer)

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `${s}s`
}

// ── 一键生成（SSE） ──
const abortCtrl = ref<AbortController | null>(null)

const canGenerate = computed(() => !!wizard.vlmImageB64 && !wizard.vlmRunning)

async function startGenerate() {
  if (!canGenerate.value) return
  wizard.vlmRunning = true
  wizard.vlmProgress = []
  wizard.vlmResults = null
  progressPct.value = 0
  startTimer()

  // 初始化进度条
  const steps = ['vlm', 'bottle', 'cap', 'wand', 'wiper', 'assembly']
  wizard.vlmProgress = steps.map(s => ({
    step: s,
    status: 'running' as const,
    message: stepLabel(s),
  }))
  // 设置第一个为 running，其余为 pending
  for (let i = 1; i < wizard.vlmProgress.length; i++) {
    ;(wizard.vlmProgress[i] as any).status = 'pending'
  }

  const ctrl = new AbortController()
  abortCtrl.value = ctrl

  try {
    const resp = await fetch('/api/vlm/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_b64: wizard.vlmImageB64,
        height_mm: wizard.vlmDims.height_mm,
      }),
      signal: ctrl.signal,
    })

    if (!resp.ok || !resp.body) {
      // 标记第一步为错误
      if (wizard.vlmProgress.length > 0) {
        wizard.vlmProgress[0] = {
          ...wizard.vlmProgress[0],
          status: 'error' as const,
          message: `HTTP ${resp.status}: ${resp.statusText}`,
        }
      }
      wizard.vlmRunning = false
      wizard.vlmResults = {}
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let completed = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // 解析 SSE 行
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const evt: VlmProgressEvent = JSON.parse(line.slice(6))
            handleProgress(evt)
            if (evt.step === 'complete') completed = true
          } catch { /* ignore parse errors */ }
        }
      }
      // 收到 complete 事件后主动断开，不再等待服务端关闭连接
      if (completed) break
    }
  } catch (e: any) {
    if (e.name !== 'AbortError') {
      console.error('VLM generate error:', e)
    }
  }

  wizard.vlmRunning = false
  stopTimer()
}

function handleProgress(evt: VlmProgressEvent) {
  // 更新总进度条
  if ((evt as any).progress !== undefined) {
    progressPct.value = (evt as any).progress
  }
  const idx = wizard.vlmProgress.findIndex(s => s.step === evt.step)
  if (idx >= 0) {
    wizard.vlmProgress[idx] = { ...wizard.vlmProgress[idx], ...evt }
    // 如果当前步骤完成，设置下一个为 running
    if (evt.status === 'done' && idx + 1 < wizard.vlmProgress.length) {
      const next = wizard.vlmProgress[idx + 1]
      if ((next as any).status === 'pending') {
        ;(wizard.vlmProgress[idx + 1] as any).status = 'running'
      }
    }
    // 如果当前步骤失败，标记后续全部为 error
    if (evt.status === 'error') {
      for (let i = idx + 1; i < wizard.vlmProgress.length; i++) {
        ;(wizard.vlmProgress[i] as any).status = 'error'
        ;(wizard.vlmProgress[i] as any).message = '已跳过'
      }
    }
  }
  // 全局错误事件（step 不在进度列表中）
  if (evt.step === 'error' && idx < 0) {
    const running = wizard.vlmProgress.findIndex(s => s.status === 'running')
    if (running >= 0) {
      wizard.vlmProgress[running] = {
        ...wizard.vlmProgress[running],
        status: 'error',
        message: evt.message || '未知错误',
      }
    }
  }
  // 完成事件
  if (evt.step === 'complete') {
    wizard.vlmResults = evt.results || {}
    if (evt.results && Object.keys(evt.results).length > 0) {
      loadResultsToViewer(evt.results)
    }
  }
}

function loadResultsToViewer(results: Record<string, any>) {
  viewerStore.clearAll()
  viewerStore.sessionSource = 'vlm'
  const comps = ['bottle', 'cap', 'wand', 'wiper']
  for (const cid of comps) {
    const r = results[cid]
    if (r?.ok && r.stl_url) {
      viewerStore.storePendingSTL(cid, r.stl_url, r.qc?.params || {})
    }
  }
  if (results.assembly?.positions) {
    viewerStore.setAssemblyPositions(results.assembly.positions)
  }
}

function stepLabel(step: string): string {
  const map: Record<string, string> = {
    vlm: 'AI 识别外形轮廓',
    bottle: '生成瓶身 (Bottle)',
    cap: '生成瓶盖 (Cap)',
    wand: '生成刷杆 (Wand)',
    wiper: '生成刮片 (Wiper)',
    assembly: '装配检查',
  }
  return map[step] || step
}

function statusIcon(status: string): string {
  if (status === 'done') return '\u2714'     // ✔
  if (status === 'error') return '\u2718'    // ✘
  if (status === 'running') return '\u25CF'  // ●
  return '\u25CB'                             // ○
}

function onViewResult() {
  viewerStore.modalOpen = true
}

function onBack() {
  wizard.goTo(0) // Landing
}

const allDone = computed(() => {
  return wizard.vlmResults !== null
})

const okCount = computed(() => {
  if (!wizard.vlmResults) return 0
  return ['bottle', 'cap', 'wand', 'wiper'].filter(
    k => wizard.vlmResults?.[k]?.ok
  ).length
})
</script>

<template>
  <div class="step-image-import">
    <!-- 上半部分：上传 + 滑动条 -->
    <div class="sim-top">
      <div
        class="sim-upload"
        @drop="onDrop"
        @dragover="onDragOver"
        @click="($refs.fileInput as HTMLInputElement)?.click()"
      >
        <img v-if="imagePreviewUrl" :src="imagePreviewUrl" class="sim-preview" />
        <div v-else class="sim-placeholder">
          <div class="sim-upload-icon">&#128247;</div>
          <div>{{ t('wizard.vlmUploadHint') }}</div>
        </div>
        <input
          ref="fileInput"
          type="file"
          accept="image/jpeg,image/png"
          style="display: none"
          @change="onFileChange"
        />
      </div>

      <div class="sim-sliders">
        <h3 class="sim-sliders-title">{{ t('wizard.vlmKeyDims') }}</h3>

        <div class="sim-slider-row">
          <label>{{ t('wizard.vlmHeight') }}</label>
          <el-slider
            v-model="wizard.vlmDims.height_mm"
            :min="30" :max="150" :step="1"
            show-input :show-input-controls="false"
            input-size="small"
          />
          <span class="sim-unit">mm</span>
        </div>

        <el-button
          type="primary"
          size="large"
          :disabled="!canGenerate"
          :loading="wizard.vlmRunning"
          class="sim-gen-btn"
          @click="startGenerate"
        >
          {{ wizard.vlmRunning ? t('wizard.vlmGenerating') : t('wizard.vlmGenerate') }}
        </el-button>
      </div>
    </div>

    <!-- 下半部分：进度 -->
    <div v-if="wizard.vlmProgress.length > 0" class="sim-progress">
      <!-- 总进度条 -->
      <div class="sim-bar-wrap">
        <div class="sim-bar-track">
          <div class="sim-bar-fill" :style="{ width: progressPct + '%' }" />
        </div>
        <span class="sim-bar-text">{{ progressPct }}%</span>
        <span v-if="wizard.vlmRunning" class="sim-bar-time">{{ formatTime(elapsed) }}</span>
      </div>

      <!-- 各步骤列表 -->
      <div
        v-for="s in wizard.vlmProgress"
        :key="s.step"
        :class="['sim-step', `sim-${s.status}`]"
      >
        <span class="sim-step-icon">{{ statusIcon(s.status) }}</span>
        <span class="sim-step-label">{{ stepLabel(s.step) }}</span>
        <span v-if="s.status === 'running' && s.step === 'vlm'" class="sim-step-msg sim-step-sub">
          {{ s.message }}
        </span>
        <span v-else-if="s.status === 'done' || s.status === 'error'" class="sim-step-msg">
          {{ s.message }}
        </span>
      </div>
    </div>

    <!-- 完成后按钮 -->
    <div v-if="allDone" class="sim-actions">
      <div class="sim-result-summary">
        {{ okCount }}/4 {{ t('wizard.vlmComponentsDone') }}
      </div>
      <div class="sim-btns">
        <el-button @click="onBack">{{ t('wizard.vlmBackToLanding') }}</el-button>
        <el-button type="primary" @click="onViewResult">
          {{ t('wizard.vlmView3D') }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.step-image-import {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}

.sim-top {
  display: flex;
  gap: 32px;
  align-items: flex-start;
}

.sim-upload {
  width: 280px;
  height: 280px;
  border: 2px dashed #cbd5e1;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  overflow: hidden;
  transition: border-color 0.2s;
  flex-shrink: 0;
}

.sim-upload:hover {
  border-color: #2563eb;
}

.sim-preview {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.sim-placeholder {
  text-align: center;
  color: #94a3b8;
}

.sim-upload-icon {
  font-size: 48px;
  margin-bottom: 8px;
}

.sim-sliders {
  flex: 1;
  min-width: 300px;
}

.sim-sliders-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0 0 20px;
  color: #1e293b;
}

.sim-slider-row {
  margin-bottom: 20px;
}

.sim-slider-row label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 6px;
}

.sim-unit {
  font-size: 12px;
  color: #94a3b8;
  margin-left: 4px;
}

.sim-gen-btn {
  width: 100%;
  margin-top: 16px;
  font-size: 16px;
  height: 44px;
}

/* 总进度条 */
.sim-bar-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
}

.sim-bar-track {
  flex: 1;
  height: 8px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}

.sim-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #10b981);
  border-radius: 4px;
  transition: width 0.4s ease;
}

.sim-bar-text {
  font-size: 13px;
  font-weight: 700;
  color: #2563eb;
  min-width: 36px;
}

.sim-bar-time {
  font-size: 12px;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}

/* 进度列表 */
.sim-progress {
  margin-top: 32px;
  border-top: 1px solid #e2e8f0;
  padding-top: 24px;
}

.sim-step {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  font-size: 14px;
  color: #64748b;
}

.sim-step-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
}

.sim-step-label {
  font-weight: 600;
  min-width: 160px;
}

.sim-step-msg {
  color: #94a3b8;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}

.sim-running {
  color: #2563eb;
}

.sim-running .sim-step-icon {
  animation: pulse 1s infinite;
}

.sim-done {
  color: #10b981;
}

.sim-error {
  color: #ef4444;
}

.sim-pending {
  color: #cbd5e1;
}

.sim-step-sub {
  color: #3b82f6 !important;
  font-style: italic;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* 完成按钮 */
.sim-actions {
  margin-top: 24px;
  text-align: center;
}

.sim-result-summary {
  font-size: 16px;
  font-weight: 700;
  color: #10b981;
  margin-bottom: 16px;
}

.sim-btns {
  display: flex;
  gap: 12px;
  justify-content: center;
}
</style>

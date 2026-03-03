import { useAppStore } from '@/stores/app'
import { useSchemaStore } from '@/stores/schema'
import { useParamsStore } from '@/stores/params'
import { useViewerStore } from '@/stores/viewer'
import * as api from '@/api/client'
import { flattenNested, setNested, deleteNested } from '@/utils/nested'
import type { GenerateResponse } from '@/api/types'
import { dlog } from '@/utils/debugLog'

let autoTimer: ReturnType<typeof setTimeout> | null = null

export interface GenerateResult {
  response: GenerateResponse | null
  error: string | null
}

export function useGenerate() {
  const appStore = useAppStore()
  const schemaStore = useSchemaStore()
  const paramsStore = useParamsStore()
  const viewerStore = useViewerStore()

  async function generate(opts?: { silent?: boolean }): Promise<GenerateResult> {
    const silent = opts?.silent ?? false
    const comp = schemaStore.currentComponent
    if (!comp || !comp.enabled) return { response: null, error: 'Component not enabled' }

    dlog.generate(`════════ 生成开始: ${appStore.componentId} ════════`)
    dlog.generate('当前参数快照', JSON.parse(JSON.stringify(paramsStore.values)))

    appStore.setGenerating(true)
    appStore.setGenMessage(silent ? '' : '')

    // Clear old state for this component (prevent self-constraint)
    try {
      await api.deleteGeneratedComponent(appStore.componentId!)
      dlog.generate(`已删除旧生成状态: ${appStore.componentId}`)
    } catch {}

    // Re-fetch constraints (without self)
    const constraints = await api.fetchConstraints(appStore.componentId!)
    dlog.generate('重新获取约束', constraints)
    paramsStore.setCrossConstraints(constraints)
    paramsStore.applyCrossConstraints()

    // Auto-fix constraint violations
    const warns = paramsStore.autoFixCrossConstraints()
    if (warns.length > 0) {
      dlog.warn('autoFix 修正了违规参数', warns)
    }

    // Build send params
    const sendParams = JSON.parse(JSON.stringify(paramsStore.values))
    dlog.generate('约束应用后的参数', JSON.parse(JSON.stringify(sendParams)))

    // Safety filter: remove params not in schema
    const schemaKeys = new Set((comp.params || []).map((pd) => pd.k))
    const flatSend = flattenNested(sendParams)
    const removed: string[] = []
    for (const fk of Object.keys(flatSend)) {
      if (!schemaKeys.has(fk)) {
        deleteNested(sendParams, fk)
        removed.push(fk)
      }
    }
    if (removed.length > 0) {
      dlog.generate('过滤掉非schema参数', removed)
    }

    // Safety clamp: enforce schema static ranges
    const flatSend2 = flattenNested(sendParams)
    const clamped: string[] = []
    for (const pd of comp.params || []) {
      if ((pd.type === 'float' || pd.type === 'int') && pd.k in flatSend2) {
        let v = Number(flatSend2[pd.k])
        if (!isNaN(v)) {
          const orig = v
          if (pd.max !== undefined && pd.max !== null && v > pd.max) {
            setNested(sendParams, pd.k, pd.max)
            clamped.push(`${pd.k}: ${orig} → ${pd.max} (schema max)`)
          }
          if (pd.min !== undefined && pd.min !== null && v < pd.min) {
            setNested(sendParams, pd.k, pd.min)
            clamped.push(`${pd.k}: ${orig} → ${pd.min} (schema min)`)
          }
        }
      }
    }
    if (clamped.length > 0) {
      dlog.warn('schema范围夹紧', clamped)
    }

    const payload = {
      product: appStore.productId!,
      component: appStore.componentId!,
      preset_id: appStore.presetId,
      params: sendParams,
      title: comp.name,
    }
    dlog.generate('最终发送 payload', payload)

    try {
      const res = await api.generate(payload)

      if (res.stl_url && appStore.componentId) {
        // 使用后端返回的完整参数（含派生参数），而非前端面板的不完整参数
        // qc.params 包含所有核心+派生参数，autoAssemble() 需要这些来精确定位
        const fullParams = (res as any).qc?.params || paramsStore.values
        viewerStore.storePendingSTL(appStore.componentId, res.stl_url, fullParams)
      }

      // 存储后端计算的装配位置（精确值，无需前端重算）
      const assembly = (res as any).assembly
      if (assembly?.positions) {
        viewerStore.setAssemblyPositions(assembly.positions)
      }

      appStore.setLastResponse(res)

      if (res.ok === false) {
        dlog.warn(`生成失败: ${res.error}`, { qc: (res as any).qc })
        appStore.setGenMessage(res.error || 'Generation failed', true)
      } else {
        const timeSec = res.time_sec ? ` (${res.time_sec}s)` : ''
        dlog.generate(`生成成功${timeSec}`, {
          qc_pass: (res as any).qc?.all_pass,
          qc_results: (res as any).qc?.results,
          final_params: (res as any).qc?.params,
        })
        appStore.setGenMessage(`OK${timeSec}`)
      }

      dlog.generate('════════ 生成结束 ════════')
      appStore.setGenerating(false)
      return { response: res, error: null }
    } catch (e: any) {
      dlog.warn(`生成异常: ${e}`)
      dlog.generate('════════ 生成结束(异常) ════════')
      appStore.setGenerating(false)
      appStore.setGenMessage(String(e), true)
      appStore.setLastResponse(null)
      return { response: null, error: String(e) }
    }
  }

  function scheduleAutoGenerate() {
    if (!appStore.autoGenerate) return
    if (autoTimer) clearTimeout(autoTimer)
    autoTimer = setTimeout(() => generate({ silent: true }), 650)
  }

  return { generate, scheduleAutoGenerate }
}

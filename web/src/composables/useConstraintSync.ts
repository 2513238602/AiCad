import { watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { useParamsStore } from '@/stores/params'
import * as api from '@/api/client'
import { recalcAllDerivedParams } from '@/composables/useDerivedRules'
import { dlog } from '@/utils/debugLog'

/**
 * Watch componentId changes and immediately fetch + apply cross-component constraints.
 * This ensures parameter sliders show correct constrained ranges as soon as
 * the user switches to a new component (not just when they click "generate").
 */
export function useConstraintSync() {
  const appStore = useAppStore()
  const paramsStore = useParamsStore()

  watch(
    () => appStore.componentId,
    async (newId) => {
      if (!newId) return
      try {
        const constraints = await api.fetchConstraints(newId)
        dlog.constraint(`组件切换 → ${newId}, 约束数: ${Object.keys(constraints).length}`)
        paramsStore.setCrossConstraints(constraints)
        paramsStore.applyCrossConstraints()
        paramsStore.autoFixCrossConstraints()

        // Recalculate derived params with locked keys respected
        const lockedKeys = new Set<string>()
        for (const [k, c] of Object.entries(constraints)) {
          if (c.locked) lockedKeys.add(k)
        }
        recalcAllDerivedParams(newId, paramsStore.values, paramsStore.setParam, lockedKeys)
      } catch (e) {
        dlog.warn('组件切换约束同步失败:', e)
      }
    },
  )
}

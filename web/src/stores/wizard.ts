import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { VlmProgressEvent } from '@/api/types'

/**
 * Wizard step identifiers.
 */
export enum WizardStep {
  Landing = 0,
  Product = 1,
  Component = 2,
  CoreParams = 3,
  Choice = 4,
  FineTune = 5,
  Generate = 6,
  ImageImport = 7,  // 独立流程：图片→一键生成
}

/**
 * Step metadata for nav display.
 */
export interface StepMeta {
  step: WizardStep
  labelKey: string // i18n key
}

export const STEPS: StepMeta[] = [
  { step: WizardStep.Landing, labelKey: 'wizard.stepLanding' },
  { step: WizardStep.Product, labelKey: 'wizard.stepProduct' },
  { step: WizardStep.Component, labelKey: 'wizard.stepComponent' },
  { step: WizardStep.CoreParams, labelKey: 'wizard.stepCoreParams' },
  { step: WizardStep.Choice, labelKey: 'wizard.stepChoice' },
  { step: WizardStep.FineTune, labelKey: 'wizard.stepFineTune' },
  { step: WizardStep.Generate, labelKey: 'wizard.stepGenerate' },
]

/**
 * Core params shown in Step 3, keyed by component id.
 */
export const CORE_PARAMS: Record<string, string[]> = {
  cap: ['outer_od_mm', 'height_mm', 'taper_deg', 'top_shape'],
  bottle: ['total_height_mm', 'body_od_mm', 'neck_od_mm', 'body_profile'],
  wand: ['outer_od_mm', 'cap_height_mm', 'stem_diameter_mm'],
  wiper: ['outer_od_mm', 'orifice_mm'],
}

/**
 * Fine-tune modules (Step 5), keyed by component id.
 * Each module has an i18n label key and a list of param key patterns.
 */
export interface FineTuneModule {
  id: string
  labelKey: string
  paramPatterns: string[] // param keys or prefixes (e.g. 'thread.')
}

export const FINE_TUNE_MODULES: Record<string, FineTuneModule[]> = {
  cap: [
    {
      id: 'inner',
      labelKey: 'wizard.moduleInner',
      paramPatterns: ['inner_id_mm', 'cavity_depth_mm', 'edge_fillet_mm'],
    },
    {
      id: 'thread',
      labelKey: 'wizard.moduleThread',
      paramPatterns: ['thread.'],
    },
    {
      id: 'grip',
      labelKey: 'wizard.moduleGrip',
      paramPatterns: ['grip.'],
    },
    {
      id: 'profile',
      labelKey: 'wizard.moduleProfile',
      paramPatterns: ['profile_mode', 'profile_points_json', 'profile_symmetry', 'profile_b_points_json'],
    },
  ],
  bottle: [
    {
      id: 'inner',
      labelKey: 'wizard.moduleInner',
      paramPatterns: [
        'inner_depth_mm',
        'wall_thickness_mm',
        'bottom_thickness_mm',
        'lip_thickness_mm',
      ],
    },
    {
      id: 'thread',
      labelKey: 'wizard.moduleThread',
      paramPatterns: ['thread.'],
    },
    {
      id: 'shoulder',
      labelKey: 'wizard.moduleShoulder',
      paramPatterns: ['shoulder_height_mm', 'shoulder_style'],
    },
    {
      id: 'bottom',
      labelKey: 'wizard.moduleBottom',
      paramPatterns: ['bottom_style'],
    },
    {
      id: 'profile',
      labelKey: 'wizard.moduleProfile',
      paramPatterns: ['profile_mode', 'profile_points_json', 'profile_symmetry', 'profile_b_points_json'],
    },
  ],
  wand: [
    {
      id: 'thread',
      labelKey: 'wizard.moduleThread',
      paramPatterns: ['thread.'],
    },
    {
      id: 'seal',
      labelKey: 'wizard.moduleSeal',
      paramPatterns: ['seal_ring.'],
    },
    {
      id: 'brush',
      labelKey: 'wizard.moduleBrush',
      paramPatterns: ['brush.'],
    },
  ],
  wiper: [
    {
      id: 'flange',
      labelKey: 'wizard.moduleFlange',
      paramPatterns: ['flange_od_mm', 'flange_id_mm', 'flange_height_mm', 'flange_position'],
    },
    {
      id: 'diaphragm',
      labelKey: 'wizard.moduleDiaphragm',
      paramPatterns: ['diaphragm_style'],
    },
  ],
}

export const useWizardStore = defineStore('wizard', () => {
  const currentStep = ref(WizardStep.Landing)
  // 独立模式：向导 / 高级 / 展览馆 / 虚拟展馆
  const appMode = ref<'wizard' | 'classic' | 'gallery' | 'showroom'>('wizard')

  // Track the highest step reached (for nav indicator)
  const highestStep = ref(WizardStep.Landing)

  // Selected fine-tune module id (Step 5)
  const activeModule = ref<string | null>(null)

  // ── 图片导入相关状态 ──
  const vlmImageB64 = ref('')
  const vlmDims = ref({ height_mm: 70 })
  const vlmProgress = ref<VlmProgressEvent[]>([])
  const vlmRunning = ref(false)
  const vlmResults = ref<Record<string, any> | null>(null)

  const isFirstStep = computed(() => currentStep.value === WizardStep.Landing)
  const isLastStep = computed(() => currentStep.value === WizardStep.Generate)

  function goTo(step: WizardStep) {
    currentStep.value = step
    if (step > highestStep.value) {
      highestStep.value = step
    }
  }

  function next() {
    if (currentStep.value < WizardStep.Generate) {
      goTo(currentStep.value + 1)
    }
  }

  function prev() {
    if (currentStep.value > WizardStep.Landing) {
      goTo(currentStep.value - 1)
    }
  }

  function reset() {
    currentStep.value = WizardStep.Landing
    highestStep.value = WizardStep.Landing
    activeModule.value = null
    vlmImageB64.value = ''
    vlmProgress.value = []
    vlmRunning.value = false
    vlmResults.value = null
  }

  function setMode(mode: 'wizard' | 'classic' | 'gallery' | 'showroom') {
    appMode.value = mode
  }

  function setActiveModule(moduleId: string | null) {
    activeModule.value = moduleId
  }

  return {
    currentStep,
    appMode,
    highestStep,
    activeModule,
    isFirstStep,
    isLastStep,
    goTo,
    next,
    prev,
    reset,
    setMode,
    setActiveModule,
    // 图片导入状态
    vlmImageB64,
    vlmDims,
    vlmProgress,
    vlmRunning,
    vlmResults,
  }
})

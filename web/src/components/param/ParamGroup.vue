<script setup lang="ts">
import type { ParamDef } from '@/api/types'
import ParamField from './ParamField.vue'

defineProps<{
  groupKey: string
  groupLabel: string
  params: ParamDef[]
}>()
</script>

<template>
  <el-collapse-item :title="groupLabel" :name="groupKey">
    <ParamField v-for="pd in params" :key="pd.k" :param-def="pd" />
  </el-collapse-item>
</template>

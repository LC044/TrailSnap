<template>
  <div class="dashboard-filters">
    <el-select v-model="period" aria-label="时间范围" class="period-select"
      ><el-option label="全部时间" value="all" /><el-option
        v-for="year in years"
        :key="year"
        :label="`${year}年`"
        :value="String(year)" /><el-option label="自定义范围" value="custom"
    /></el-select>
    <el-select
      v-model="passenger"
      aria-label="乘车人"
      placeholder="全部乘车人"
      filterable
      class="passenger-select"
      ><el-option label="全部乘车人" value="" /><el-option
        v-for="name in passengers"
        :key="name"
        :label="name"
        :value="name"
    /></el-select>
    <el-select
      v-model="transport"
      aria-label="交通方式"
      class="transport-select"
      ><el-option label="全部交通方式" value="all" /><el-option
        v-for="mode in transportKinds"
        :key="mode.key"
        :label="mode.label"
        :value="mode.key"
    /></el-select>
    <button
      class="ts-icon-button ts-button-secondary"
      aria-label="刷新统计"
      :disabled="loading"
      @click="emit('refresh')"
    >
      <RefreshCw :class="{ 'animate-spin': loading }" class="h-4 w-4" />
    </button>
  </div>
</template>
<script setup lang="ts">
import { RefreshCw } from "lucide-vue-next";
import { transportKinds } from "@/utils/ticketStatistics";
defineProps<{ years: number[]; passengers: string[]; loading?: boolean }>();
const period = defineModel<string>("period", { required: true });
const passenger = defineModel<string>("passenger", { required: true });
const transport = defineModel<string>("transport", { required: true });
const emit = defineEmits<{ refresh: [] }>();
</script>
<style scoped>
.dashboard-filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  min-width: 0;
}
.period-select {
  width: 130px;
}
.passenger-select {
  width: 150px;
}
.transport-select {
  width: 160px;
}
@media (max-width: 639px) {
  .dashboard-filters {
    display: grid;
    width: 100%;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 40px;
    gap: 8px;
  }
  .period-select,
  .passenger-select,
  .transport-select {
    width: 100%;
    min-width: 0;
  }
  .transport-select {
    grid-column: 1/3;
    grid-row: 2;
  }
  .dashboard-filters > button {
    grid-column: 3;
    grid-row: 1;
    width: 40px;
  }
}
</style>

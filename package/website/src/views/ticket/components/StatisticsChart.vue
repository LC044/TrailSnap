<template>
  <div
    ref="container"
    class="statistics-chart"
    role="img"
    :aria-label="label"
  />
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import type { EChartsCoreOption } from "echarts/core";
import { echarts } from "@/utils/echarts";

const props = defineProps<{ option: EChartsCoreOption; label: string }>();
const emit = defineEmits<{
  select: [name: string];
  itemSelect: [item: { name: string; data: unknown; seriesType?: string }];
  viewport: [viewport: { center: [number, number]; zoom: number }];
}>();
const container = ref<HTMLDivElement>();
let chart: ReturnType<typeof echarts.init> | undefined;
let observer: ResizeObserver | undefined;
onMounted(() => {
  if (!container.value) return;
  chart = echarts.init(container.value);
  chart.setOption(props.option, { notMerge: true });
  chart.on("click", (params) => {
    if (params.name) emit("select", params.name);
    emit("itemSelect", {
      name: params.name,
      data: params.data,
      seriesType: params.seriesType,
    });
  });
  chart.on("georoam", () => {
    const geo = (
      chart?.getOption().geo as
        Array<{ center: [number, number]; zoom: number }> | undefined
    )?.[0];
    if (geo?.center)
      emit("viewport", { center: [...geo.center], zoom: geo.zoom });
  });
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(container.value);
});
watch(
  () => props.option,
  (option) => chart?.setOption(option, { notMerge: true }),
);
defineExpose({
  zoom: (factor: number) =>
    chart?.dispatchAction({ type: "geoRoam", zoom: factor }),
});
onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>

<style scoped>
.statistics-chart {
  width: 100%;
  min-width: 0;
  height: 100%;
  min-height: 180px;
}
</style>

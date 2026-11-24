<template>
  <div class="space-y-6 animate-fade-in">
    <!-- 标题 / 面包屑 -->
    <div>
      <div class="flex items-center gap-2 mb-1">
        <BackButton v-if="scope === 'province'" label="返回全国" @click="emit('drill-up')" />
        <div class="min-w-0">
          <p class="la-eyebrow"><span class="la-eyebrow-dot" aria-hidden="true"></span>位置图鉴 · ATLAS PUZZLE</p>
          <h2 class="la-title mt-1 truncate">
            {{ scope === 'nation' ? '全国照片拼图' : activeProvince }}
          </h2>
        </div>
      </div>
      <p class="text-xs text-gray-500 dark:text-gray-400">
        {{
          scope === 'nation'
            ? '用照片拼出你走过的中国，点击任意省份查看单省拼图'
            : '点击任意格子可替换或移除该位置的照片'
        }}
      </p>
    </div>

    <!-- 统计 -->
    <div class="puzzle-stats grid grid-cols-2">
      <div class="puzzle-stat">
        <div class="la-stat-label">拼图格子</div>
        <div class="la-stat-value">{{ cellCount.toLocaleString() }}</div>
      </div>
      <div class="puzzle-stat">
        <div class="la-stat-label">使用照片</div>
        <div class="la-stat-value">{{ usedPhotoCount.toLocaleString() }}</div>
      </div>
    </div>

    <!-- 选片策略 -->
    <div>
      <h3 class="la-panel-kicker mb-2 flex items-center gap-1.5">
        <Sparkles class="w-3.5 h-3.5 text-primary-500" /> 选片策略
      </h3>
      <el-select
        :model-value="config.strategy"
        class="w-full"
        size="default"
        @update:model-value="(v: PhotoStrategy) => update('strategy', v)"
      >
        <el-option label="回忆价值优先" value="memory_score" />
        <el-option label="画质优先" value="quality_score" />
        <el-option label="最新拍摄优先" value="photo_time" />
        <el-option label="随机" value="random" />
        <el-option label="手动选择" value="manual" />
      </el-select>
      <p class="text-[11px] text-gray-400 dark:text-gray-500 mt-1.5 leading-relaxed">
        {{
          config.strategy === 'manual'
            ? '手动模式：点击任意格子自行选择照片，选择会按省份保存在本地，刷新不丢。'
            : '评分来自 AI 分析结果，未分析的照片会自动排在后面。'
        }}
      </p>
    </div>

    <!-- 数量 -->
    <div>
      <div class="flex items-center justify-between mb-1">
        <h3 class="la-panel-kicker">拼图精细度</h3>
        <span class="text-xs font-medium text-primary-600 dark:text-primary-400 tabular-nums">
          {{ config.targetCount }}
        </span>
      </div>
      <el-slider
        :model-value="config.targetCount"
        :min="countRange.min"
        :max="countRange.max"
        :step="countRange.step"
        :show-tooltip="false"
        @update:model-value="(v: number | number[]) => update('targetCount', v as number)"
      />
      <p class="text-[11px] text-gray-400 dark:text-gray-500 leading-relaxed">
        {{
          scope === 'nation'
            ? '数值越大格子越小、照片用得越多。各省格子数按面积分配，照片不足时自动放大格子。'
            : '数值越大格子越小、轮廓越精细。照片不足时会自动放大格子避免重复。'
        }}
      </p>
    </div>

    <!-- 开关与操作 -->
    <div class="space-y-3">
      <label
        class="flex items-center justify-between cursor-pointer group"
      >
        <span class="la-panel-kicker">显示区域名称</span>
        <el-switch
          :model-value="config.showLabel"
          @update:model-value="(v: string | number | boolean) => update('showLabel', Boolean(v))"
        />
      </label>

      <button
        class="w-full py-2.5 rounded-xl bg-primary-500 hover:bg-primary-600 text-white text-sm font-medium transition-colors flex items-center justify-center gap-2 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
        :disabled="loading || config.strategy === 'manual'"
        :title="config.strategy === 'manual' ? '手动模式下不支持换一批' : undefined"
        @click="emit('reshuffle')"
      >
        <Shuffle class="w-4 h-4" />
        换一批照片
      </button>
    </div>

    <!-- Top 省份快捷入口（仅全国图） -->
    <div v-if="scope === 'nation' && topRegions.length">
      <h3 class="la-panel-kicker mb-3 flex items-center gap-1.5">
        <Trophy class="w-3.5 h-3.5 text-primary-500" /> 照片最多的省份
      </h3>
      <div class="space-y-2">
        <button
          v-for="(item, index) in topRegions"
          :key="item.name"
          class="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors text-left focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          @click="emit('drill-down', item.name)"
        >
          <span
            class="puzzle-rank shrink-0"
          >
            {{ String(index + 1).padStart(2, '0') }}
          </span>
          <span class="flex-1 text-sm text-gray-700 dark:text-gray-200 truncate">{{ item.name }}</span>
          <span class="text-xs text-gray-500 dark:text-gray-400 shrink-0">{{ item.count }} 张</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import BackButton from '@/components/ui/BackButton.vue'
import { computed } from 'vue'
import { Shuffle, Sparkles, Trophy } from 'lucide-vue-next'
import type { PhotoStrategy, PuzzleConfig, PuzzleScope } from '@/composables/useMapPuzzle'

const props = defineProps<{
  scope: PuzzleScope
  activeProvince: string | null
  config: PuzzleConfig
  cellCount: number
  usedPhotoCount: number
  regionCounts: Map<string, number>
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'update-config', patch: Partial<PuzzleConfig>): void
  (e: 'drill-down', provinceName: string): void
  (e: 'drill-up'): void
  (e: 'reshuffle'): void
}>()

/**
 * 滑块范围。
 *
 * 全国图上限取 3000：格子数按面积分配，而单省占全国面积很小（陕西仅 2.12%），
 * 原先 2000 的上限下陕西只能用到 47 张。实测再往上调收益递减 ——
 * 6000 时格子边长降到 6.3px，照片已经看不清，且最坏情况需加载 4687 张缩略图。
 */
const countRange = computed(() =>
  props.scope === 'nation'
    ? { min: 200, max: 3000, step: 100 }
    : { min: 20, max: 400, step: 10 }
)

const topRegions = computed(() =>
  [...props.regionCounts.entries()]
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([name, count]) => ({ name, count }))
)

const update = <K extends keyof PuzzleConfig>(key: K, value: PuzzleConfig[K]) => {
  emit('update-config', { [key]: value } as Partial<PuzzleConfig>)
}
</script>

<style scoped>
.puzzle-stats {
  border-top: 1px solid var(--ts-color-border);
  border-bottom: 1px solid var(--ts-color-border);
}
.puzzle-stat {
  min-width: 0;
  padding: 12px 10px 13px;
  border-left: 1px solid var(--ts-color-border);
}
.puzzle-stat:first-child { border-left: 0; padding-left: 0; }
.puzzle-stat:last-child { padding-right: 0; }
.puzzle-rank {
  width: 22px;
  color: var(--ts-color-text-tertiary);
  font-family: var(--lm-font-display);
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}
</style>

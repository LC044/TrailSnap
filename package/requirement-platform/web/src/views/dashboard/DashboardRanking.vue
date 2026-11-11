<template>
  <article class="panel ranking-card">
    <div class="card-head">
      <div class="card-title"><h2>贡献与热度</h2><p>谁在提需求，哪些需求最受关注</p></div>
      <div class="seg" role="tablist" aria-label="排行维度">
        <button type="button" role="tab" :class="{ active: tab === 'contributors' }" :aria-selected="tab === 'contributors'" @click="tab = 'contributors'">提交人</button>
        <button type="button" role="tab" :class="{ active: tab === 'followed' }" :aria-selected="tab === 'followed'" :disabled="!followed.length" @click="tab = 'followed'">关注最多</button>
      </div>
    </div>

    <div v-if="tab === 'contributors'" class="rank-list">
      <div v-for="(person, index) in contributors" :key="person.user_id" class="rank-row" :title="`${person.name}：提交 ${person.count} 条需求`">
        <span class="rank-badge" :class="`rank-${index + 1}`">{{ index + 1 }}</span>
        <span class="avatar" :style="{ width: '28px', height: '28px', fontSize: '12px', ...avatarColor(person.name) }">{{ person.name.slice(0, 1) }}</span>
        <span class="rank-name">{{ person.name }}</span>
        <span class="rank-track"><i :style="{ width: `${person.pct}%` }"></i></span>
        <strong>{{ person.count }}</strong>
      </div>
      <p v-if="!contributors.length" class="chart-empty">暂无提交人数据</p>
      <div class="rank-foot">
        <span>参与人数 <b>{{ data.contributor_count }}</b></span>
        <span v-if="data.active_contributors_30d !== undefined">近 30 天活跃 <b>{{ data.active_contributors_30d }}</b></span>
        <span v-if="data.anonymous">另有 <b>{{ data.anonymous }}</b> 条匿名提交</span>
      </div>
    </div>

    <div v-else class="rank-list">
      <button v-for="(item, index) in followed" :key="item.id" type="button" class="rank-row followed-row"
        :disabled="!item.public_number" :title="item.public_number ? `查看 REQ-${item.public_number}` : '该需求暂无公开编号'"
        @click="open(item.public_number)">
        <span class="rank-badge" :class="`rank-${index + 1}`">{{ index + 1 }}</span>
        <span class="followed-title">{{ item.title }}</span>
        <span v-if="item.public_number" class="req-number">REQ-{{ item.public_number }}</span>
        <span class="followers"><el-icon :size="13"><Star /></el-icon>{{ item.follower_count }}</span>
      </button>
      <p v-if="!followed.length" class="chart-empty">暂无关注数据</p>
      <div class="rank-foot"><span>关注总数 <b>{{ data.follower_count }}</b></span><span>按关注人数排序</span></div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Star } from '@element-plus/icons-vue'
import type { Dashboard } from '../../api'
import { avatarColor } from '../../labels'

const props = defineProps<{ data: Dashboard }>()
const emit = defineEmits<{ 'open-detail': [number: number] }>()
const tab = ref<'contributors' | 'followed'>('contributors')

const maxCount = computed(() => Math.max(1, ...(props.data.top_contributors ?? []).map(person => person.count)))
const contributors = computed(() => (props.data.top_contributors ?? []).map(person => ({
  ...person, pct: (person.count / maxCount.value) * 100,
})))
const followed = computed(() => props.data.top_followed ?? [])
function open(number?: number | null) {
  if (number) emit('open-detail', number)
}
</script>

<style scoped>
.ranking-card { margin-bottom: 0; min-width: 0; }
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.card-title h2 { margin: 0; font-size: 17px; }
.card-title p { margin: 4px 0 0; font-size: 12px; color: var(--rp-text-3); }
.seg { display: inline-flex; padding: 3px; border-radius: 9px; background: #f1f5f9; }
.seg button { min-height: 26px; padding: 0 10px; border: 0; border-radius: 7px; background: transparent; color: var(--rp-text-2); font-size: 12px; cursor: pointer; transition: background .15s, color .15s, box-shadow .15s; }
.seg button.active { background: #fff; color: var(--rp-primary); font-weight: 700; box-shadow: 0 1px 4px rgba(15,23,42,.1); }
.seg button:disabled { opacity: .4; cursor: not-allowed; }
.seg button:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 1px; }
.rank-list { margin-top: 12px; }
.rank-row { display: flex; align-items: center; gap: 9px; width: 100%; min-height: 42px; padding: 5px 4px; border: 0; border-bottom: 1px solid #f4f7fb; background: transparent; text-align: left; }
.rank-row:last-of-type { border-bottom: 0; }
.followed-row { cursor: pointer; border-radius: 8px; }
.followed-row:hover:not(:disabled) { background: #f8fafc; }
.followed-row:disabled { cursor: default; opacity: .65; }
.followed-row:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 1px; }
.rank-badge { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; flex: none; border-radius: 6px; background: #f1f5f9; color: var(--rp-text-3); font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums; }
.rank-badge.rank-1 { background: #fff3d6; color: #b45309; }
.rank-badge.rank-2 { background: #eef2f7; color: #64748b; }
.rank-badge.rank-3 { background: #fdeee2; color: #c2683a; }
.rank-name { min-width: 0; width: 88px; flex: none; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: 12.5px; color: var(--rp-text-2); }
.rank-track { flex: 1; min-width: 24px; height: 8px; border-radius: 999px; background: #f1f5f9; overflow: hidden; }
.rank-track i { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #60a5fa, #2563eb); transition: width .45s ease; }
.rank-row strong { width: 32px; flex: none; text-align: right; font-size: 12.5px; color: var(--rp-text); font-variant-numeric: tabular-nums; }
.followed-title { flex: 1; min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: 12.5px; color: var(--rp-text); }
.req-number { flex: none; padding: 2px 6px; border-radius: 5px; background: var(--rp-primary-soft); color: var(--rp-primary); font-size: 10.5px; font-weight: 600; }
.followers { display: inline-flex; align-items: center; gap: 3px; width: 38px; flex: none; justify-content: flex-end; color: var(--rp-text-2); font-size: 12px; font-variant-numeric: tabular-nums; }
.followers .el-icon { color: #f59e0b; }
.rank-foot { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--rp-border); font-size: 11.5px; color: var(--rp-text-3); }
.rank-foot b { color: var(--rp-text); font-variant-numeric: tabular-nums; }
.chart-empty { margin: 24px 0; text-align: center; color: var(--rp-text-3); font-size: 12.5px; }
@media (max-width: 720px) {
  .rank-name { width: 72px; }
  .req-number { display: none; }
}
</style>

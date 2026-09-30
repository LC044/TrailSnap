<template>
  <main
    ref="pageElement"
    class="relation-page min-h-full bg-gray-50 pb-24 text-gray-900 dark:bg-gray-950 dark:text-gray-100 md:pb-10"
  >
    <div class="mx-auto max-w-screen-2xl px-[var(--ts-page-gutter)] pt-3 md:pt-7">
      <section
        class="cover relative isolate overflow-hidden rounded-[28px] bg-gray-900 text-white shadow-xl md:rounded-[36px]"
      >
        <img
          v-if="store.page?.center.photo_id"
          :src="thumbnailUrl(store.page.center.photo_id, 'medium')"
          alt=""
          class="absolute inset-0 h-full w-full object-cover"
        />
        <div class="cover-shade absolute inset-0"></div>
        <div class="cover-glow absolute inset-0"></div>
        <div class="relative flex h-full flex-col justify-between p-5 sm:p-7 md:p-10">
          <div class="flex items-start justify-between gap-3">
            <button class="cover-icon" aria-label="返回上一页" @click="back">←</button>
            <div class="flex gap-2">
              <button class="cover-tool" :aria-expanded="searchOpen" @click="openSearch">换个起点</button>
              <button class="cover-tool" :aria-pressed="store.comparing" @click="toggleComparing">
                {{ store.comparing ? '完成选择' : '寻找交集' }}
              </button>
            </div>
          </div>
          <div class="max-w-3xl">
            <nav
              v-if="store.visits.length"
              class="mb-5 flex items-center gap-2 overflow-x-auto text-xs text-white/80"
              aria-label="探索路径"
            >
              <template v-for="(visit, index) in store.visits" :key="visit.root">
                <button class="shrink-0 underline-offset-4 hover:underline" @click="restore(index)">
                  {{ visit.label }}
                </button>
                <span aria-hidden="true">/</span>
              </template>
              <span class="truncate text-white">{{ store.page?.center.label }}</span>
            </nav>
            <p class="mb-3 text-xs font-semibold tracking-[0.22em] text-white/75">
              {{
                store.page
                  ? `从这${store.page.center.type === 'person' ? '个人' : store.page.center.type === 'place' ? '个地方' : store.page.center.type === 'memory' ? '段记忆' : '张照片'}出发`
                  : 'TRAILSNAP · 记忆漫游'
              }}
            </p>
            <h1 class="cover-title max-w-2xl text-4xl font-semibold leading-tight sm:text-5xl md:text-6xl">
              {{ store.page?.center.label || '沿着记忆，遇见更多故事' }}
            </h1>
            <p class="mt-3 max-w-xl text-sm leading-relaxed text-white/80 md:text-base">
              {{
                store.page?.center.subtitle ||
                (store.page
                  ? '顺着照片与记忆，看看这段故事还通向哪里。'
                  : '选一个人、一处地点或一段记忆，看看它还连接着什么。')
              }}
            </p>
            <div v-if="store.page" class="mt-6 flex flex-wrap items-center gap-3">
              <button class="cover-primary" @click="details(store.page.center)">
                {{ detailLabel(store.page.center) }} <span aria-hidden="true">↗</span>
              </button>
              <span class="text-xs text-white/75">{{ store.page.nodes.length }} 条可继续探索的线索</span>
            </div>
          </div>
        </div>
      </section>

      <section
        v-if="searchOpen || !root"
        class="discovery mt-5 rounded-[28px] border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900 sm:p-7"
        aria-label="选择探索对象"
      >
        <div class="mb-5 flex items-start justify-between gap-4">
          <div>
            <p class="eyebrow">开始一段漫游</p>
            <h2 class="mt-1 text-2xl font-semibold">想从哪里开始？</h2>
          </div>
          <button v-if="root" class="quiet-icon" aria-label="关闭选择对象" @click="searchOpen = false">
            ×
          </button>
        </div>
        <div class="mb-4 flex flex-wrap gap-2" aria-label="搜索对象类型">
          <button
            v-for="kind in kinds"
            :key="kind"
            class="pill"
            :class="searchType === kind ? 'pill-active' : ''"
            :aria-pressed="searchType === kind"
            @click="setSearchType(kind)"
          >
            {{ relationLabels[kind] }}
          </button>
        </div>
        <form class="flex gap-2" @submit.prevent="search(false)">
          <input
            v-model="searchText"
            class="search-field min-w-0 flex-1"
            :placeholder="`找找${relationLabels[searchType]}…`"
            aria-label="搜索对象"
            maxlength="200"
          />
          <button class="solid-button shrink-0" :disabled="searching">
            {{ searching ? '寻找中…' : '寻找' }}
          </button>
        </form>
        <p v-if="locationHint" class="mt-2 text-xs text-gray-500 dark:text-gray-400">
          请选择具体地点，同名地点会分别显示。
        </p>
        <div class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <button
            v-for="node in searchResults?.items || []"
            :key="node.id"
            class="discovery-card group overflow-hidden rounded-2xl bg-gray-50 text-left dark:bg-gray-800"
            @click="choose(node)"
          >
            <div class="relative aspect-[4/3] overflow-hidden bg-gray-200 dark:bg-gray-700">
              <img
                v-if="node.photo_id"
                :src="thumbnailUrl(node.photo_id, 'small')"
                alt=""
                class="h-full w-full object-cover transition duration-300 group-hover:scale-105"
                loading="lazy"
              />
              <span
                v-else
                class="flex h-full items-center justify-center text-3xl text-gray-400 dark:text-gray-500"
                >{{ nodeIcon(node.type) }}</span
              >
            </div>
            <span class="block p-3"
              ><strong class="block truncate text-sm">{{ node.label }}</strong
              ><span class="mt-1 block truncate text-xs text-gray-500 dark:text-gray-400">{{
                node.subtitle || relationLabels[node.type]
              }}</span></span
            >
          </button>
        </div>
        <p v-if="searchError" role="alert" class="mt-4 text-sm">搜索失败，请重试。</p>
        <p
          v-else-if="searchResults && !searchResults.items.length"
          class="mt-4 text-sm text-gray-500 dark:text-gray-400"
        >
          没有找到可用对象，试试别的关键词。
        </p>
        <button
          v-if="searchResults?.has_more"
          class="text-link mt-5"
          :disabled="searching"
          @click="search(true)"
        >
          继续浏览 →
        </button>
      </section>

      <div
        v-if="store.error"
        role="alert"
        class="mt-5 flex items-center justify-between rounded-2xl bg-white p-5 dark:bg-gray-900"
      >
        <span>{{ store.error }}</span
        ><button class="text-link" @click="loadRoot">重试</button>
      </div>
      <p v-if="store.loading" role="status" class="mt-6 text-sm text-primary-600 dark:text-primary-400">
        正在寻找与你有关的线索…
      </p>

      <template v-if="store.page">
        <section class="mt-8 md:mt-10" aria-label="关联内容">
          <div class="mb-5 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p class="eyebrow">继续发现</p>
              <h2 class="mt-1 text-2xl font-semibold md:text-3xl">故事从这里延伸</h2>
              <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">轻触一条线索，接着往前走。</p>
            </div>
            <button v-if="wideGraph" class="text-link text-sm" @click="listView = !listView">
              {{ listView ? '观看关系图' : '浏览全部线索' }} →
            </button>
          </div>
          <div class="mb-5 flex gap-2 overflow-x-auto pb-1" aria-label="关联类型筛选">
            <button
              v-for="kind in kinds"
              :key="kind"
              class="pill shrink-0"
              :class="store.types.includes(kind) ? 'pill-active' : ''"
              :aria-pressed="store.types.includes(kind)"
              :disabled="store.loading"
              @click="filter(kind)"
            >
              {{ nodeIcon(kind) }} {{ relationLabels[kind] }}
            </button>
          </div>

          <div
            v-if="(wideGraph || graphFullscreen) && !listView && store.page.nodes.length"
            class="graph-stage grid overflow-hidden border border-gray-800 bg-gray-950 shadow-xl lg:grid-cols-[minmax(0,1fr)_300px]"
            :class="graphFullscreen ? 'fixed inset-0 z-[1000] h-screen rounded-none' : 'rounded-[28px]'"
          >
            <div class="graph-surface relative min-w-0 p-5 md:p-7" :class="graphFullscreen ? 'flex min-h-0 flex-col' : ''">
              <div class="relative z-10 flex items-center justify-between gap-3 text-xs tracking-widest text-white/60">
                <p>关联脉络 · {{ store.page.center.label }} · {{ store.canvasNodes.length }} 个节点</p>
                <button class="rounded-lg border border-white/20 px-3 py-2 text-sm tracking-normal text-white transition hover:bg-white/10" @click="graphFullscreen = !graphFullscreen">
                  {{ graphFullscreen ? '退出全屏' : '全屏漫游' }} ⤢
                </button>
              </div>
              <RelationGraph
                :nodes="store.canvasNodes"
                :edges="store.canvasEdges"
                :positions="store.canvasPositions"
                :expanded="store.canvasExpanded"
                :cursors="store.canvasCursors"
                :root-id="store.page.center.id"
                :loading-id="store.canvasLoading"
                :zoom="store.zoom"
                :pan="store.pan"
                :focus-id="focusedNode?.id || null"
                :fullscreen="graphFullscreen"
                :class="graphFullscreen ? 'flex-1' : ''"
                @pan="store.pan = $event"
                @zoom="store.zoom = $event"
                @choose="chooseGraph"
                @inspect="focusedNode = $event"
              />
            </div>
            <aside
              class="overflow-y-auto border-t border-white/10 bg-white/5 p-5 text-white lg:border-l lg:border-t-0"
              aria-label="线索预览"
            >
              <p class="text-xs tracking-widest text-white/60">眼前的线索</p>
              <template v-if="activeNode">
                <img
                  v-if="activeNode.photo_id"
                  :src="thumbnailUrl(activeNode.photo_id, 'medium')"
                  alt=""
                  class="mt-5 aspect-[4/3] w-full rounded-2xl object-cover"
                />
                <div
                  v-else
                  class="mt-5 flex aspect-[4/3] items-center justify-center rounded-2xl bg-white/10 text-5xl"
                >
                  {{ nodeIcon(activeNode.type) }}
                </div>
                <p class="mt-5 text-xs text-white/60">{{ relationLabels[activeNode.type] }}</p>
                <h3 class="mt-1 break-words text-2xl font-semibold">{{ activeNode.type === 'photo' ? '照片里的这一刻' : activeNode.label }}</h3>
                <p v-if="activeNode.subtitle" class="mt-1 text-sm text-white/60">{{ activeNode.subtitle }}</p>
                <p class="mt-4 text-sm leading-relaxed text-white/80">{{ summary(activeNode) }}</p>
                <button
                  class="mt-5 w-full rounded-xl bg-white px-4 py-3 text-sm font-semibold text-gray-950 transition hover:bg-gray-100 dark:bg-gray-100 dark:text-gray-950"
                  :disabled="Boolean(store.canvasLoading) || (store.canvasExpanded.includes(activeNode.id) && !store.canvasCursors[activeNode.id])"
                  @click="chooseGraph(activeNode)"
                >
                  {{ store.comparing ? '选择这条线索' : store.canvasLoading === activeNode.id ? '正在展开…' : store.canvasExpanded.includes(activeNode.id) ? store.canvasCursors[activeNode.id] ? '继续展开' : '已展开' : '展开下一层' }} →
                </button>
                <p v-if="store.canvasError" role="alert" class="mt-2 text-xs text-rose-300">{{ store.canvasError }}</p>
                <button
                  v-if="activeNode.id !== store.page.center.id"
                  class="mt-3 w-full py-2 text-sm text-white/75 underline-offset-4 hover:underline"
                  @click="showEvidence(activeNode, graphParent(activeNode))"
                >
                  看看它们如何相连
                </button>
                <button class="mt-1 w-full py-2 text-sm text-white/75 underline-offset-4 hover:underline" @click="details(activeNode)">{{ detailLabel(activeNode) }} ↗</button>
              </template>
              <div class="mt-5 grid grid-cols-4 gap-2 lg:grid-cols-4" aria-label="其他线索">
                <button
                  v-for="node in store.canvasNodes.slice(-8)"
                  :key="node.id"
                  class="aspect-square overflow-hidden rounded-lg border-2"
                  :class="activeNode?.id === node.id ? 'border-white' : 'border-transparent'"
                  :aria-label="`预览${node.label}`"
                  @click="focusedNode = node"
                >
                  <img
                    v-if="node.photo_id"
                    :src="thumbnailUrl(node.photo_id, 'small')"
                    alt=""
                    class="h-full w-full object-cover"
                    loading="lazy"
                  />
                  <span v-else class="flex h-full items-center justify-center bg-white/10 text-lg">{{
                    nodeIcon(node.type)
                  }}</span>
                </button>
              </div>
            </aside>
          </div>

          <div v-else class="space-y-9">
            <section v-for="kind in store.types" :key="kind" v-show="group(kind).length">
              <div class="mb-4 flex items-center gap-3">
                <span class="text-xl" aria-hidden="true">{{ nodeIcon(kind) }}</span>
                <h3 class="text-xl font-semibold">{{ sectionTitle(kind) }}</h3>
                <span class="text-xs text-gray-400 dark:text-gray-500">{{
                  store.page.nodes.filter((node) => node.type === kind).length
                }}</span>
              </div>
              <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <article
                  v-for="node in group(kind)"
                  :key="node.id"
                  class="story-card group relative overflow-hidden rounded-[22px] border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900"
                >
                  <button
                    class="flex w-full items-start gap-4 p-3 text-left sm:block"
                    :aria-label="`${store.comparing ? '选择' : '探索'}${node.label}`"
                    @click="choose(node)"
                  >
                    <span
                      class="relative block h-24 w-24 shrink-0 overflow-hidden rounded-2xl bg-gray-100 dark:bg-gray-800 sm:aspect-[4/3] sm:h-auto sm:w-full"
                    >
                      <img
                        v-if="node.photo_id"
                        :src="thumbnailUrl(node.photo_id, 'medium')"
                        alt=""
                        class="h-full w-full object-cover transition duration-300 group-hover:scale-105"
                        loading="lazy"
                      />
                      <span
                        v-else
                        class="flex h-full items-center justify-center text-3xl text-gray-400 dark:text-gray-500"
                        >{{ nodeIcon(kind) }}</span
                      >
                    </span>
                    <span class="block min-w-0 flex-1 pt-1 sm:px-1 sm:pt-4"
                      ><span class="block text-[11px] text-primary-600 dark:text-primary-400">{{
                        relationLabels[kind]
                      }}</span
                      ><strong class="mt-1 block break-words text-base leading-snug sm:text-lg">{{
                        node.label
                      }}</strong
                      ><span
                        v-if="node.subtitle"
                        class="mt-1 block truncate text-xs text-gray-500 dark:text-gray-400"
                        >{{ node.subtitle }}</span
                      ><span class="mt-2 block text-xs leading-relaxed text-gray-600 dark:text-gray-300">{{
                        summary(node)
                      }}</span
                      ><span
                        class="mt-3 inline-block text-sm font-medium text-primary-600 dark:text-primary-400"
                        >{{ store.comparing ? '选中这条线索' : '继续探索' }} →</span
                      ></span
                    >
                    <span
                      v-if="store.selected.some((item) => item.id === node.id)"
                      class="absolute right-4 top-4 flex h-7 w-7 items-center justify-center rounded-full bg-primary-500 text-white"
                      aria-label="已选择"
                      >✓</span
                    >
                  </button>
                  <div
                    class="flex items-center justify-between gap-2 border-t border-gray-100 px-4 py-2 dark:border-gray-800"
                  >
                    <button class="subtle-link" @click="showEvidence(node)">如何相连？</button>
                    <button class="subtle-link" @click="details(node)">{{ detailLabel(node) }} ↗</button>
                  </div>
                </article>
              </div>
              <button
                v-if="
                  mobile &&
                  !expandedKinds.has(kind) &&
                  (store.page?.nodes.filter((node) => node.type === kind).length || 0) > 6
                "
                class="text-link mt-4"
                @click="expandedKinds.add(kind)"
              >
                展开更多{{ relationLabels[kind] }} →
              </button>
            </section>
          </div>

          <div
            v-if="!store.page.nodes.length"
            class="rounded-[24px] border border-gray-200 bg-white px-5 py-12 text-center dark:border-gray-800 dark:bg-gray-900"
          >
            <span class="text-4xl">✧</span>
            <p class="mt-3 font-medium">这条线索还没有延伸出去</p>
            <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">换一种类型，或从另一个对象继续探索。</p>
          </div>
          <div
            v-if="store.page.nodes.length"
            class="mt-7 flex items-center justify-between gap-4 border-t border-gray-200 pt-5 dark:border-gray-800"
          >
            <p class="text-xs text-gray-500 dark:text-gray-400">
              已找到 {{ store.page.nodes.length }} 条线索
            </p>
            <div class="flex gap-4">
              <button
                v-if="store.previousCursors.length"
                class="text-link"
                :disabled="store.loading"
                @click="previousPage"
              >
                ← 上一页</button
              ><button
                v-if="store.page.has_more"
                class="text-link"
                :disabled="store.loading"
                @click="nextPage"
              >
                继续发现 →
              </button>
            </div>
          </div>
        </section>
      </template>

      <section
        v-if="pair.length === 2"
        ref="resultsElement"
        class="mt-10 scroll-mt-5 rounded-[28px] border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900 sm:p-7"
        aria-label="共同记忆结果"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="eyebrow">{{ evidenceMode ? '连接的理由' : '两条线索的交集' }}</p>
            <h2 class="mt-1 text-2xl font-semibold">
              {{ evidenceMode ? '它们如何相连' : '共同的记忆' }}
            </h2>
            <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">
              {{ pair[0].label }} 与 {{ pair[1].label }}
            </p>
          </div>
          <button class="quiet-icon" aria-label="关闭结果" @click="closeResults">×</button>
        </div>
        <p
          class="mt-4 rounded-xl bg-gray-50 p-3 text-xs leading-relaxed text-gray-500 dark:bg-gray-800 dark:text-gray-400"
        >
          这里展示的是共同记忆和直接关联的照片。同一记忆不代表两人同框，也不代表到访了同一地点。
        </p>
        <p v-if="resultLoading" role="status" class="mt-5 text-sm">正在寻找共同片段…</p>
        <p v-if="resultError" role="alert" class="mt-5 text-sm">
          加载失败。<button class="text-link" @click="loadResults">重试</button>
        </p>
        <div v-for="kind in evidenceKinds" :key="kind" class="mt-7">
          <h3 class="mb-4 text-lg font-semibold">{{ kind === 'memory' ? '共同记忆' : '直接关联的照片' }}</h3>
          <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <button
              v-for="node in results[kind]?.items || []"
              :key="node.id"
              class="discovery-card overflow-hidden rounded-2xl bg-gray-50 text-left dark:bg-gray-800"
              @click="details(node)"
            >
              <span class="block aspect-[4/3] overflow-hidden bg-gray-200 dark:bg-gray-700"
                ><img
                  v-if="node.photo_id"
                  :src="thumbnailUrl(node.photo_id, 'medium')"
                  alt=""
                  class="h-full w-full object-cover"
                  loading="lazy"
                /><span
                  v-else
                  class="flex h-full items-center justify-center text-3xl text-gray-400 dark:text-gray-500"
                  >{{ nodeIcon(kind) }}</span
                ></span
              ><span class="block p-3"
                ><strong class="block truncate text-sm">{{ node.label }}</strong
                ><span class="mt-1 block truncate text-xs text-gray-500 dark:text-gray-400">{{
                  node.subtitle
                }}</span></span
              >
            </button>
          </div>
          <p
            v-if="results[kind] && !results[kind]?.items.length"
            class="text-sm text-gray-500 dark:text-gray-400"
          >
            {{ kind === 'memory' ? '暂时没有共同记忆。' : '暂时没有直接关联的照片。' }}
          </p>
          <button
            v-if="results[kind]?.has_more"
            class="text-link mt-4"
            :disabled="resultLoading"
            @click="moreResults(kind)"
          >
            继续浏览{{ relationLabels[kind] }} →
          </button>
        </div>
      </section>

      <div
        v-if="store.comparing"
        class="compare-bar fixed bottom-[84px] left-3 right-3 z-20 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-primary-200 bg-white/95 p-3 shadow-2xl backdrop-blur dark:border-primary-800 dark:bg-gray-900/95 md:bottom-5 md:left-[260px] md:right-7 md:p-4"
      >
        <div class="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto">
          <span v-if="!store.selected.length" class="text-sm text-gray-600 dark:text-gray-300"
            >选择两个对象，看看它们共有的回忆</span
          ><button
            v-for="node in store.selected"
            :key="node.id"
            class="pill max-w-40 shrink-0 truncate"
            @click="select(node)"
          >
            {{ node.label }} ×</button
          ><span v-if="store.selected.length === 1" class="shrink-0 text-xs text-gray-500 dark:text-gray-400"
            >再选一个</span
          >
        </div>
        <button class="solid-button shrink-0" :disabled="store.selected.length !== 2" @click="compare">
          查看交集 →
        </button>
      </div>
    </div>
    <PhotoLightbox
      v-if="photo"
      :visible="true"
      :image="photo"
      :images="[photo]"
      :current-index="0"
      :has-prev="false"
      :has-next="false"
      @close="closePhoto"
      @confirm-delete="closePhoto"
    />
  </main>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { useAppBack } from '@/composables/useAppBack'
import { ElMessage } from 'element-plus'
import { relationsApi } from '@/api/relations'
import { albumService } from '@/api/album'
import { faceApi } from '@/api/face'
import { locationService } from '@/api/location'
import { useRelationStore } from '@/stores/relationStore'
import { useLocationStore } from '@/stores/locationStore'
import { mapPhotoToImage } from '@/stores/photoStore'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { relationLabels, type RelationNode, type RelationResults, type RelationType } from '@/types/relations'
import type { AlbumImage, FaceIdentity } from '@/types/album'
import PhotoLightbox from '@/components/PhotoLightbox.vue'

const RelationGraph = defineAsyncComponent(() => import('@/components/relations/RelationGraph.vue'))
const kinds: RelationType[] = ['person', 'place', 'memory', 'photo']
const evidenceKinds: ('memory' | 'photo')[] = ['memory', 'photo']
const store = useRelationStore()
const locationStore = useLocationStore()
store.checkScope()
const returnToSource = useAppBack('/memories')
const route = useRoute(),
  router = useRouter()
const root = computed(() => {
  const key = typeof route.query.root === 'string' ? route.query.root : ''
  return /^(person|memory|photo|place:scene):/.test(key) ? key.replaceAll('-', '') : key
})
const mobile = useMediaQuery('(max-width: 767px)')
const wideGraph = useMediaQuery('(min-width: 1280px)')
const listView = ref(false),
  searchOpen = ref(false),
  searching = ref(false),
  searchError = ref(false)
const searchType = ref<RelationType>('person'),
  searchText = ref('')
const locationHint = computed(() => (typeof route.query.placeName === 'string' ? route.query.placeName : ''))
const searchResults = ref<RelationResults | null>(null)
const albumOrigins = ref<RelationNode[]>([])
const { resultPair: pair, evidenceMode } = storeToRefs(store)
const resultLoading = ref(false),
  resultError = ref(false)
const results = ref<{ memory: RelationResults | null; photo: RelationResults | null }>({
  memory: null,
  photo: null,
})
const photo = ref<AlbumImage | null>(null)
let searchGeneration = 0,
  resultGeneration = 0,
  detailGeneration = 0
let disposed = false
let handledRoot = ''
const pageElement = ref<HTMLElement>()
const resultsElement = ref<HTMLElement>()
const expandedKinds = ref(new Set<RelationType>())
const focusedNode = ref<RelationNode | null>(null)
const graphFullscreen = ref(false)
let originalOverflow = ''
watch(graphFullscreen, (value) => {
  if (value) {
    originalOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  } else document.body.style.overflow = originalOverflow
})
function graphKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && graphFullscreen.value) graphFullscreen.value = false
}
watch(
  () => store.page,
  () => {
    focusedNode.value = null
  },
)
const activeNode = computed(() => {
  const nodes = store.canvasNodes
  return nodes.find((node) => node.id === focusedNode.value?.id) || nodes[1] || nodes[0] || null
})
let scrollContainer: Element | null = null
function nodeIcon(kind: RelationType) {
  return { person: '◉', place: '⌖', memory: '✧', photo: '▧' }[kind]
}
function sectionTitle(kind: RelationType) {
  return {
    person: '遇见的人',
    place: '相连的地方',
    memory: '牵出的记忆',
    photo: '留下的照片',
  }[kind]
}
function openSearch() {
  searchOpen.value = !searchOpen.value
  if (searchOpen.value) {
    searchText.value = ''
    void search(false)
  }
}
function setSearchType(kind: RelationType) {
  searchType.value = kind
  searchText.value = ''
  void search(false)
}
function toggleComparing() {
  store.comparing = !store.comparing
  if (!store.comparing) store.selected = []
}
function rememberScroll() {
  store.scroll = scrollContainer?.scrollTop || 0
}
async function setScroll(value: number) {
  await nextTick()
  scrollContainer?.scrollTo(0, value)
}
onMounted(() => {
  window.addEventListener('keydown', graphKeydown)
  scrollContainer = pageElement.value?.parentElement?.closest('main') || document.scrollingElement
  scrollContainer?.addEventListener('scroll', rememberScroll, { passive: true })
  void setScroll(store.scroll)
  const left = route.query.left,
    right = route.query.right
  if (typeof left === 'string' && typeof right === 'string' && left !== right) {
    pair.value = [left, right].map((id) => ({
      id,
      type: id.split(':')[0] as RelationType,
      label: '正在加载对象',
      subtitle: '',
      photo_id: null,
      detail_target: null,
    }))
    evidenceMode.value = route.query.evidence === '1'
    store.comparing = !evidenceMode.value
  }
  if (pair.value.length === 2) void loadResults()
})

function group(kind: RelationType) {
  const items = store.page?.nodes.filter((node) => node.type === kind) || []
  return mobile.value && !expandedKinds.value.has(kind) ? items.slice(0, 6) : items
}
function summary(node: RelationNode) {
  if (node.id === store.page?.center.id) return '从这里继续发现更多关联。'
  return store.canvasEdges.find((edge) => edge.target === node.id || edge.source === node.id)?.evidence_summary || ''
}
function graphParent(node: RelationNode) {
  const id = store.canvasParents[node.id]
  return store.canvasNodes.find((item) => item.id === id) || store.page?.center || node
}
async function chooseGraph(node: RelationNode) {
  focusedNode.value = node
  if (store.comparing) {
    select(node)
    return
  }
  const seen = new Set(store.canvasNodes.map((item) => item.id))
  const added = await store.expandCanvas(node.id)
  if (!added) return
  const points = [node, ...store.canvasNodes.filter((item) => !seen.has(item.id))]
    .map((item) => store.canvasPositions[item.id])
    .filter((point) => Boolean(point))
  const xs = points.map((point) => point.x), ys = points.map((point) => point.y)
  store.pan = [-(Math.min(...xs) + Math.max(...xs)) * store.zoom / 2, -(Math.min(...ys) + Math.max(...ys)) * store.zoom / 2]
}
function detailLabel(node: RelationNode) {
  return node.id.startsWith('place:unresolved:') ? '查看来源记忆' : '查看详情'
}
async function search(append: boolean) {
  const ticket = ++searchGeneration
  searching.value = true
  searchError.value = false
  try {
    if (searchType.value === 'person' || searchType.value === 'place') {
      let origins = albumOrigins.value
      if (!append) {
        if (searchType.value === 'person') {
          const identities: FaceIdentity[] = []
          const limit = 1000
          for (let page = 1; ; page++) {
            const batch = await faceApi.listIdentities(page, limit, ['named', 'unnamed'])
            identities.push(...batch)
            if (batch.length < limit) break
          }
          origins = identities.map((identity) => ({
            id: `person:${identity.id.replaceAll('-', '')}`,
            type: 'person',
            label: identity.identity_name,
            subtitle: `${identity.face_count} 个项目`,
            photo_id: identity.cover_photo?.photo_id || null,
            detail_target: { kind: 'person', id: identity.id },
          }))
        } else {
          const [cities, provinces, districts, scenes] = await Promise.all([
            locationService.getLocations('city', 0, 10000),
            locationService.getLocations('province', 0, 10000),
            locationService.getLocations('district', 0, 10000),
            locationService.getScenesList(0, 10000),
          ])
          const preferredLevel = locationStore.level === 'photo-map' ? 'city' : locationStore.level
          const levels: ('city' | 'province' | 'district' | 'scene')[] = ['city', 'province', 'district', 'scene']
          levels.sort((a, b) => Number(b === preferredLevel) - Number(a === preferredLevel))
          const placeGroups = { city: cities, province: provinces, district: districts }
          const places = {
            ...Object.fromEntries((['city', 'province', 'district'] as const).map((level) => [
              level,
              placeGroups[level].map((place) => ({
                id: `place:album:${level}:${place.name}`,
                type: 'place' as const,
                label: place.name,
                subtitle: `${place.count} 个项目`,
                photo_id: place.cover?.id || null,
                detail_target: { kind: 'place' as const, name: place.name, level },
              })),
            ])) as Record<'city' | 'province' | 'district', RelationNode[]>,
            scene: scenes.map((scene) => ({
              id: `place:album:scene:${scene.id}`,
              type: 'place' as const,
              label: scene.name,
              subtitle: `${scene.photo_count || 0} 个项目`,
              photo_id: scene.cover?.id || null,
              detail_target: { kind: 'place' as const, name: scene.name, level: 'scene', sceneId: scene.id },
            })),
          }
          origins = levels.flatMap((level) => places[level])
        }
      }
      if (disposed || ticket !== searchGeneration) return
      albumOrigins.value = origins
      const matches = origins.filter((node) => node.label.includes(searchText.value.trim()))
      const offset = append ? Number(searchResults.value?.next_cursor || 0) : 0
      const items = [...(append ? searchResults.value?.items || [] : []), ...matches.slice(offset, offset + 20)]
      const next = offset + 20
      searchResults.value = { items, has_more: next < matches.length, next_cursor: next < matches.length ? String(next) : null }
      return
    }
    const response = await relationsApi.search(
      searchType.value,
      searchText.value,
      append ? searchResults.value?.next_cursor : null,
    )
    if (disposed || ticket !== searchGeneration) return
    const old = append ? searchResults.value?.items || [] : []
    response.items = [...new Map([...old, ...response.items].map((node) => [node.id, node])).values()]
    searchResults.value = response
  } catch {
    if (ticket === searchGeneration) searchError.value = true
  } finally {
    if (ticket === searchGeneration) searching.value = false
  }
}
async function navigate(node: RelationNode) {
  if (store.page?.center.id === node.id) return
  rememberScroll()
  const earlier = store.visits.findIndex((visit) => visit.root === node.id)
  if (earlier >= 0) {
    await restore(earlier)
    return
  }
  if (await store.explore(node.id)) {
    handledRoot = node.id
    await router.push({ path: '/explore/relations', query: { root: node.id } })
    searchOpen.value = false
    await setScroll(0)
  }
}
async function choose(node: RelationNode) {
  if (node.id.startsWith('place:album:')) {
    try {
      let cursor: string | null = null
      let found: RelationNode | undefined
      do {
        const page = await relationsApi.search('place', node.label, cursor)
        found = page.items.find((item) => item.label === node.label &&
          item.detail_target?.level === node.detail_target?.level &&
          (!node.detail_target?.sceneId || item.detail_target?.sceneId === node.detail_target.sceneId))
        cursor = page.next_cursor
      } while (!found && cursor)
      if (!found) {
        ElMessage.info('这个地点暂时没有可探索的关联。')
        return
      }
      node = found
    } catch {
      ElMessage.error('地点加载失败，请重试。')
      return
    }
  }
  if (store.comparing) select(node)
  else await navigate(node)
}
function select(node: RelationNode) {
  store.comparing = true
  if (!store.toggle(node)) ElMessage.info('最多选择两个对象，请先移除一个。')
  closeResults()
}
async function loadRoot() {
  if (!root.value) return
  const index = store.visits.findIndex((item) => item.root === root.value)
  const visit = store.visits[index]
  if (visit) {
    store.types = [...visit.types]
    if (await store.explore(root.value, 'restore', visit.cursor)) {
      store.zoom = visit.zoom
      store.pan = visit.pan
      store.visits = store.visits.slice(0, index)
      store.previousCursors = visit.previousCursors
      await setScroll(visit.scroll)
    }
  } else {
    const same = store.page?.center.id === root.value
    const savedScroll = same ? store.scroll : 0
    const cursors = same ? [...store.previousCursors] : []
    if (await store.explore(root.value, 'restore', same ? store.cursor : null)) {
      store.previousCursors = cursors
      await setScroll(savedScroll)
    }
  }
}
async function restore(index: number) {
  const visit = store.visits[index]
  if (visit) await router.push({ path: '/explore/relations', query: { root: visit.root } })
}
function back() {
  if (store.visits.length) void restore(store.visits.length - 1)
  else void returnToSource()
}
async function filter(kind: RelationType) {
  const old = [...store.types]
  const next = old.includes(kind) ? old.filter((item) => item !== kind) : [...old, kind]
  if (!next.length) {
    ElMessage.info('请至少选择一种类型。')
    return
  }
  store.types = next
  if (store.page && !(await store.explore(store.page.center.id, 'filter'))) store.types = old
}
async function nextPage() {
  if (!store.page) return
  const previous = store.cursor
  if (await store.explore(store.page.center.id, 'page', store.page.next_cursor))
    store.previousCursors.push(previous)
}
async function previousPage() {
  if (!store.page) return
  const previous = store.previousCursors.at(-1) || null
  if (await store.explore(store.page.center.id, 'page', previous)) store.previousCursors.pop()
}
function closeResults() {
  ++resultGeneration
  pair.value = []
  results.value = { memory: null, photo: null }
  resultLoading.value = false
  if (route.query.left || route.query.right)
    void router.replace({ query: { ...route.query, left: undefined, right: undefined, evidence: undefined } })
}
async function loadResults() {
  if (pair.value.length !== 2) return
  const ticket = ++resultGeneration
  resultLoading.value = true
  resultError.value = false
  results.value = { memory: null, photo: null }
  try {
    const [a, b] = pair.value
    const [memories, photos] = await Promise.all([
      relationsApi.evidence(a.id, b.id, 'memory'),
      relationsApi.evidence(a.id, b.id, 'photo'),
    ])
    if (disposed || ticket !== resultGeneration) return
    pair.value = memories.objects || pair.value
    if (!evidenceMode.value) store.selected = [...pair.value]
    results.value = { memory: memories, photo: photos }
  } catch (cause: any) {
    if (ticket !== resultGeneration) return
    resultError.value = true
    if (cause?.code === 404) {
      closeResults()
      store.selected = []
      ElMessage.info('比较对象已不可用，请重新选择。')
    }
  } finally {
    if (ticket === resultGeneration) resultLoading.value = false
  }
}
async function moreResults(kind: 'memory' | 'photo') {
  if (pair.value.length !== 2 || !results.value[kind]?.next_cursor) return
  const ticket = ++resultGeneration
  resultLoading.value = true
  try {
    const response = await relationsApi.evidence(
      pair.value[0].id,
      pair.value[1].id,
      kind,
      results.value[kind]?.next_cursor,
    )
    if (disposed || ticket !== resultGeneration) return
    response.items = [
      ...new Map(
        [...(results.value[kind]?.items || []), ...response.items].map((node) => [node.id, node]),
      ).values(),
    ]
    results.value[kind] = response
  } catch {
    if (ticket === resultGeneration) resultError.value = true
  } finally {
    if (ticket === resultGeneration) resultLoading.value = false
  }
}
async function compare() {
  pair.value = [...store.selected]
  evidenceMode.value = false
  await router.replace({
    query: { ...route.query, left: pair.value[0].id, right: pair.value[1].id, evidence: undefined },
  })
  void loadResults()
  await nextTick()
  resultsElement.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
async function showEvidence(node: RelationNode, source?: RelationNode) {
  if (!store.page) return
  pair.value = [source || store.page.center, node]
  evidenceMode.value = true
  await router.replace({
    query: { ...route.query, left: pair.value[0].id, right: pair.value[1].id, evidence: '1' },
  })
  void loadResults()
  await nextTick()
  resultsElement.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
async function details(node: RelationNode) {
  rememberScroll()
  const target = node.detail_target
  if (!target) return
  if (target.kind === 'person') await router.push(`/album/people/${target.id}`)
  else if (target.kind === 'memory') await router.push(`/memories/${target.id}`)
  else if (target.kind === 'place')
    await router.push({
      name: 'LocationDetail',
      params: { name: target.name },
      query: { level: target.level, sceneId: target.sceneId, place_key: target.place_key },
    })
  else if (target.id) {
    const ticket = ++detailGeneration
    try {
      const rows = await albumService.getPhotosByIds([target.id])
      if (!disposed && ticket === detailGeneration && rows[0]) photo.value = mapPhotoToImage(rows[0])
    } catch {
      ElMessage.error('照片已不可用或加载失败。')
    }
  }
}
function closePhoto() {
  photo.value = null
  void loadRoot()
}
watch(
  () => route.query.root,
  async (_, __, onCleanup) => {
    let cancelled = false
    onCleanup(() => { cancelled = true })
    if (root.value && handledRoot === root.value) {
      handledRoot = ''
      return
    }
    if (root.value) await loadRoot()
    else {
      store.page = null
      if (locationHint.value) {
        searchType.value = 'place'
        searchText.value = locationHint.value
      } else if (!route.query.left && !route.query.right) {
        // Look through all visible people: the self tag may be beyond the first page.
        const ticket = searchGeneration
        const initialSearchText = searchText.value
        const interrupted = () => cancelled || disposed || ticket !== searchGeneration ||
          searchText.value !== initialSearchText || store.comparing
        try {
          const limit = 100
          for (let page = 1; ; page++) {
            const identities = await faceApi.listIdentities(page, limit, ['named', 'unnamed'], 0)
            if (interrupted()) return
            const self = identities.find((identity) => identity.tags?.includes('自己'))
            if (self) {
              await router.replace({
                query: { ...route.query, root: `person:${self.id.replaceAll('-', '')}` },
              })
              return
            }
            if (identities.length < limit) break
          }
        } catch {
          // The starting-point picker remains available if the lookup fails.
        }
        if (interrupted()) return
      }
      await search(false)
    }
  },
  { immediate: true },
)
onBeforeRouteLeave(() => {
  ++searchGeneration
  ++resultGeneration
  ++detailGeneration
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', graphKeydown)
  if (graphFullscreen.value) document.body.style.overflow = originalOverflow
  disposed = true
  ++searchGeneration
  ++resultGeneration
  ++detailGeneration
  scrollContainer?.removeEventListener('scroll', rememberScroll)
})
</script>

<style scoped>
.cover {
  min-height: 350px;
}
.cover-shade {
  background:
    linear-gradient(90deg, rgb(9 16 29 / 89%), rgb(9 16 29 / 48%) 75%),
    linear-gradient(0deg, rgb(9 16 29 / 65%), transparent 65%);
}
.cover-glow {
  background: radial-gradient(ellipse at 75% 18%, rgba(var(--theme-rgb), 0.38), transparent 58%);
  mix-blend-mode: screen;
}
.cover-title {
  text-wrap: balance;
  text-shadow: 0 2px 22px rgb(0 0 0 / 35%);
}
.cover-icon,
.cover-tool {
  @apply flex min-h-11 items-center justify-center rounded-full border border-white/25 bg-black/20 px-4 text-sm text-white backdrop-blur transition hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white;
}
.cover-icon {
  @apply w-11 px-0 text-xl;
}
.cover-primary {
  @apply min-h-11 rounded-full bg-white px-5 py-2 text-sm font-semibold text-gray-950 transition hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white dark:bg-gray-100 dark:text-gray-950;
}
.eyebrow {
  @apply text-xs font-semibold tracking-[0.18em] text-primary-600 dark:text-primary-400;
}
.pill {
  @apply min-h-10 rounded-full border border-gray-200 bg-white px-4 py-2 text-sm text-gray-600 transition hover:border-primary-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-40 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300;
}
.pill-active {
  @apply border-primary-500 bg-primary-50 text-primary-600 dark:border-primary-500 dark:bg-primary-900/30 dark:text-primary-400;
}
.search-field {
  @apply min-h-12 rounded-xl border border-gray-200 bg-gray-50 px-4 text-sm outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 dark:border-gray-700 dark:bg-gray-800;
}
.solid-button {
  @apply min-h-11 rounded-xl bg-primary-500 px-5 text-sm font-semibold text-white transition hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-40;
}
.text-link {
  @apply min-h-10 text-sm font-medium text-primary-600 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-40 dark:text-primary-400;
}
.quiet-icon {
  @apply flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gray-100 text-2xl text-gray-700 transition hover:bg-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700;
}
.subtle-link {
  @apply min-h-9 text-xs text-gray-500 underline-offset-4 hover:text-primary-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-400 dark:hover:text-primary-400;
}
.story-card,
.discovery-card {
  @apply transition duration-200 hover:-translate-y-0.5 hover:shadow-lg focus-within:ring-2 focus-within:ring-primary-500;
}
.graph-surface {
  background-image:
    radial-gradient(rgb(255 255 255 / 12%) 1px, transparent 1px),
    radial-gradient(ellipse at 50% 50%, rgba(var(--theme-rgb), 0.12), transparent 70%);
  background-size:
    24px 24px,
    100% 100%;
}
@media (max-width: 767px) {
  .cover {
    min-height: 335px;
  }
  .cover-tool {
    @apply px-3 text-xs;
  }
}
</style>

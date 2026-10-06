<template>
  <div class="ts-browse-page album-library mx-auto w-full max-w-screen-2xl px-[var(--ts-page-gutter)] pb-6 pt-0 sm:py-6">
    <!-- Header -->
    <div class="ts-browse-header mb-5 flex items-center justify-between gap-3 sm:mb-8">
      <div class="min-w-0">
        <h1 class="ts-page-title text-gray-900 dark:text-white">相册</h1>

      </div>
      <div class="ts-liquid-glass ts-glass-toolbar flex shrink-0" aria-label="相册工具栏">
        <button class="ts-glass-button" aria-label="搜索相册" :aria-expanded="showAlbumSearch" @click="showAlbumSearch = !showAlbumSearch"><Search class="h-5 w-5" /></button>
        <div class="relative">
          <button class="ts-glass-button" aria-label="新建相册" :aria-expanded="showCreateActions" aria-haspopup="menu" @click="showAlbumActions = false; showCreateActions = !showCreateActions"><Plus class="h-5 w-5" /></button>
          <AdaptiveMenu v-model="showCreateActions" title="新建相册" mobile-presentation="popover" glass>
            <button v-for="kind in createKinds" :key="kind.value" class="ts-action-row" @click="showCreateActions = false; openCreateModal(kind.value)"><component :is="kind.icon" /><span>{{ kind.label }}</span></button>
          </AdaptiveMenu>
        </div>
        <button class="ts-glass-button" aria-label="更多相册操作" :aria-expanded="showAlbumActions" aria-haspopup="menu" @click="showAlbumActions = !showAlbumActions"><MoreHorizontal class="h-5 w-5" /></button>
    <AdaptiveMenu mobile-presentation="popover" v-model="showAlbumActions" title="相册整理" glass>
      <button class="ts-action-row" @click="showAlbumActions = false; showSectionSettings = true"><SlidersHorizontal />分组排序与显示</button>
      <button class="ts-action-row" @click="showAlbumActions = false; startTravelAlbum()"><WandSparkles />AI 整理旅行</button>
      <button class="ts-action-row" @click="showAlbumActions = false; startAlbumDoctor()"><Stethoscope />相册体检</button>
      <button class="ts-action-row" @click="showAlbumActions = false; startMemoryDetective()"><SearchCheck />回忆侦探</button>
      <button class="ts-action-row" @click="showAlbumActions = false; router.push('/agent/actions')"><History />操作记录</button>
    </AdaptiveMenu>
      </div>
    </div>

    <div v-if="showAlbumSearch" class="mb-5">
      <input v-model="albumSearch" aria-label="相册名称" placeholder="搜索相册名称" type="search" class="ts-input w-full" />
    </div>


    <div class="album-sections flex flex-col gap-8">
    <!-- Custom Albums Section -->
    <section v-if="!store.hiddenSections.includes('mine')" :style="{ order: sectionRank('mine') }">
      <h2 class="mb-3 sm:mb-4"><button class="ts-section-title flex min-h-11 w-full items-center gap-2 text-gray-800 dark:text-gray-100" :aria-expanded="!collapsed.mine" @click="collapsed.mine = !collapsed.mine">
        <ChevronDown class="h-4 w-4" :class="{ '-rotate-90': collapsed.mine }" />我的相册
      </button></h2>
      <div v-show="!collapsed.mine">
      
      <div v-if="visibleAlbums.length > 0" class="album-cover-strip">
        <div
          v-for="album in visibleAlbums"
          :key="album.id"
          class="album-cover-card group relative cursor-pointer rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
          role="button"
          tabindex="0"
          :aria-label="`打开相册 ${album.title}`"
          @click="navigateToAlbum(album.id)"
          @keydown.enter="navigateToAlbum(album.id)"
          @keydown.space.prevent="navigateToAlbum(album.id)"
          @touchstart="album.type !== 'system' ? onAlbumTouchStart(album, $event) : undefined"
        >
          <!-- Cover -->
          <div class="relative mb-2.5 aspect-square overflow-hidden rounded-2xl border border-gray-100 bg-gray-100 shadow-sm transition-all duration-300 group-hover:shadow-md dark:border-gray-800 dark:bg-gray-800 sm:mb-3 sm:rounded-xl">
            <img
              :src="album.cover.thumbnail"
              :alt="`${album.title}的封面`"
              class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
              loading="lazy"
            />
            <!-- Overlay -->
            <div class="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors"></div>
            <!-- Type Badge -->
            <div class="absolute left-2 top-2 flex gap-1">
               <span v-if="album.type === 'smart'" class="bg-primary-600/90 backdrop-blur-sm text-white text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                 <Sparkles class="w-3 h-3 text-white" /> 智能
               </span>
               <span v-if="album.type === 'conditional'" class="bg-primary-500/90 backdrop-blur-sm text-white text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                 <Filter class="w-3 h-3 text-white" /> 条件
               </span>
            </div>

            <!-- Actions (Only for User Albums) -->
            <div v-if="album.type !== 'system'" class="absolute right-2 top-2 z-10 hidden gap-1.5 opacity-0 transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100 md:flex md:group-hover:opacity-100">
              <button
                type="button"
                @click.stop="openEditModal(album)"
                class="flex h-9 w-9 items-center justify-center rounded-full bg-white/90 text-gray-600 shadow-sm backdrop-blur-sm hover:text-primary-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:bg-gray-800/90 dark:text-gray-300"
                title="编辑"
                :aria-label="`编辑相册 ${album.title}`"
              >
                <Edit2 class="w-4 h-4" />
              </button>
              <button
                type="button"
                @click.stop="confirmDelete(album)"
                class="flex h-9 w-9 items-center justify-center rounded-full bg-white/90 text-gray-600 shadow-sm backdrop-blur-sm hover:text-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:bg-gray-800/90 dark:text-gray-300"
                title="删除"
                :aria-label="`删除相册 ${album.title}`"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>
          <!-- Info -->
          <div class="px-0.5">
            <h3 class="ts-card-title truncate text-sm font-semibold text-gray-900 dark:text-white sm:text-base sm:font-bold">{{ album.title }}</h3>
            <div class="flex justify-between items-center mt-1">
              <p class="text-xs text-gray-500 dark:text-gray-400">{{ album.count }} 个项目</p>
              <!-- <p class="text-xs text-gray-400 dark:text-gray-400">{{ formatDate(album.createdAt) }}</p> -->
            </div>
          </div>
        </div>
      </div>
      
      <!-- Empty State for Custom Albums -->
      <div v-else class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-gray-200 bg-gray-50 px-4 py-12 text-center text-gray-400 dark:text-gray-500 dark:border-gray-800 dark:bg-gray-800/50 sm:py-20">
        <div class="w-16 h-16 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center mb-4">
          <FolderOpen class="w-8 h-8 text-gray-300 dark:text-gray-600" />
        </div>
        <p>{{ albumSearch ? '没有匹配的相册' : '暂无自定义相册' }}</p>
        <button type="button" @click="openCreateModal('user')" class="ts-button ts-button-ghost mt-4 text-primary-600 dark:text-primary-400">创建第一个相册</button>
      </div>
      </div>
    </section>

    <section v-if="!store.hiddenSections.includes('memories')" :style="{ order: sectionRank('memories') }">
      <h2 class="mb-3 flex items-center gap-2">
        <button class="ts-section-title flex min-h-11 flex-1 items-center gap-2 text-left text-gray-900 dark:text-white" :aria-expanded="!collapsed.memories" @click="collapsed.memories = !collapsed.memories"><ChevronDown class="h-4 w-4" :class="{ '-rotate-90': collapsed.memories }" />回忆</button>
        <button class="min-h-11 text-xs text-gray-500 dark:text-gray-400" aria-label="查看全部回忆" @click="router.push('/memories')">{{ memoryTotal }} <ChevronRight class="inline h-4 w-4" /></button>
      </h2>
      <div v-show="!collapsed.memories">
        <div v-if="memoryPreviews.length" class="album-cover-strip" @scroll.passive="onMemoryScroll">
          <RouterLink v-for="memory in memoryPreviews" :key="memory.id" :to="`/memories/${memory.id}`" class="album-cover-card text-left">
            <div class="relative aspect-square overflow-hidden rounded-[22px] bg-gray-100 dark:bg-gray-800">
              <img v-if="memory.cover_photo_id" :src="thumbnailUrl(memory.cover_photo_id, 'small')" :alt="memory.title" class="h-full w-full object-cover" loading="lazy" />
              <BookHeart v-else class="absolute left-1/2 top-1/2 h-10 w-10 -translate-x-1/2 -translate-y-1/2 text-primary-500" />
            </div>
            <p class="ts-card-title mt-2 truncate text-gray-900 dark:text-white">{{ memory.title }}</p>
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ memory.photo_count }} 张照片</p>
          </RouterLink>
          <button v-if="memoryPreviews.length < memoryTotal" class="album-cover-card text-sm text-primary-500" :disabled="memoryLoading" @click="loadMemoryPreviews(true)">{{ memoryLoading ? '加载中…' : memoryLoadError ? '加载失败，点击重试' : '加载更多' }}</button>
        </div>
        <div v-else class="ts-surface flex min-h-20 items-center gap-3 px-4">
          <BookHeart class="h-7 w-7 text-primary-500" /><p class="text-sm text-gray-500 dark:text-gray-400">{{ memoryLoading ? '正在加载回忆…' : memoryLoadError ? '回忆加载失败' : '确认后的记忆会显示在这里' }}</p>
          <button v-if="memoryLoadError" class="ml-auto min-h-11 text-sm text-primary-500" @click="loadMemoryPreviews()">重试</button>
        </div>
      </div>
    </section>

    <section v-if="!store.hiddenSections.includes('tickets')" :style="{ order: sectionRank('tickets') }">
      <h2 class="mb-3 flex items-center gap-2"><button class="ts-section-title min-h-11 flex-1 text-left" :aria-expanded="!collapsed.tickets" @click="collapsed.tickets = !collapsed.tickets">票夹</button><RouterLink to="/ticket" class="min-h-11 flex items-center text-xs text-primary-600 dark:text-primary-400">查看全部</RouterLink></h2>
      <TicketWalletPreview v-if="!collapsed.tickets" />
    </section>

    <section v-for="group in visibleSmartAlbums" :key="group.id" :style="{ order: sectionRank(group.id) }">
      <h2 class="mb-3 flex items-center gap-2">
        <button class="ts-section-title flex min-h-11 flex-1 items-center gap-2 text-left text-gray-900 dark:text-white" :aria-expanded="!collapsed[group.id]" @click="collapsed[group.id] = !collapsed[group.id]">
          <ChevronDown class="h-4 w-4" :class="{ '-rotate-90': collapsed[group.id] }" />{{ group.title }}
        </button>
        <button class="min-h-11 text-xs text-gray-500 dark:text-gray-400" :aria-label="`查看全部${group.title}`" @click="navigateToSmartAlbum(group)">{{ smartOverviewLoading ? '加载中' : formatSmartCount(group.data?.item_count) }} <ChevronRight class="inline h-4 w-4" /></button>
      </h2>
      <div v-show="!collapsed[group.id]">
      <div v-if="group.data?.representatives?.length" class="album-cover-strip" @scroll.passive="onGroupScroll(group.id, $event)">
        <button v-for="item in group.data.representatives" :key="item.entity_id" class="album-cover-card text-left" @click="openRepresentative(group, item)">
          <div class="relative aspect-square overflow-hidden rounded-[22px]">
            <SmartAlbumCover :type="group.id" :icon="group.icon" :data="{ item_count: 1, photo_count: item.photo_count, representatives: [item] }" :alt-prefix="item.name" />
            <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-transparent px-3 pb-3 pt-8 text-white">
              <p class="text-xs">{{ formatSmartCount(item.photo_count) }} 张</p><p class="ts-card-title truncate">{{ item.name || '未命名' }}</p>
            </div>
          </div>
        </button>
        <button v-if="group.data.representatives.length < group.data.item_count" class="album-cover-card flex items-center justify-center text-sm text-primary-500" :disabled="store.sectionLoading[group.id]" @click="store.loadMoreSection(group.id)">{{ store.sectionLoading[group.id] ? '加载中…' : store.sectionErrors[group.id] ? '加载失败，点击重试' : '加载更多' }}</button>
      </div>
      <button v-else class="flex min-h-20 w-full items-center gap-3 rounded-2xl bg-white px-4 text-left dark:bg-gray-900" @click="navigateToSmartAlbum(group)">
        <span class="text-sm text-gray-500 dark:text-gray-400">{{ smartOverviewLoading ? '正在加载封面…' : group.emptyDescription }}</span><ChevronRight class="ml-auto h-4 w-4 text-gray-500 dark:text-gray-400" />
      </button>
      </div>
    </section>
    </div>
    <ResponsiveDialog v-model="showSectionSettings" title="相册分组设置" glass>
      <p class="mb-3 text-sm text-gray-500 dark:text-gray-400">调整分组顺序，选择相册页显示的分组。</p>
      <div v-for="(section, index) in store.sections" :key="section.id" class="flex min-h-14 items-center gap-2 border-b border-gray-100 dark:border-gray-800">
        <label class="flex min-h-11 flex-1 items-center gap-3"><input type="checkbox" :checked="!store.hiddenSections.includes(section.id)" class="h-4 w-4 accent-primary-500" @change="store.toggleSection(section.id)" />{{ section.title }}</label>
        <button class="ts-icon-button" :aria-label="`上移${section.title}`" :disabled="index === 0" @click="store.moveSection(section.id, -1)"><ArrowUp class="h-4 w-4" /></button>
        <button class="ts-icon-button" :aria-label="`下移${section.title}`" :disabled="index === store.sections.length - 1" @click="store.moveSection(section.id, 1)"><ArrowDown class="h-4 w-4" /></button>
      </div>
    </ResponsiveDialog>
    <ResponsiveDialog v-model="showContextMenu" :title="contextMenuAlbum?.title || '相册操作'" glass @close="closeContextMenu">
      <button class="ts-action-row" @click="editFromContextMenu"><Edit2 />编辑相册</button>
      <button class="ts-action-row danger" @click="deleteFromContextMenu"><Trash2 />删除相册</button>
    </ResponsiveDialog>

    <!-- Create/Edit Modal -->
    <ResponsiveDialog
      v-model="showModal"
      :title="`${isEditing ? '编辑' : '新建'}${albumTypeLabel}`"
      :description="albumFormDescription"
      max-width="34rem"
      :mobile-mode="isMobile ? 'fullscreen' : 'sheet'"
      mobile-back
      :close-on-backdrop="!loading"
      :close-on-escape="!loading"
    >
      <form id="album-details-form" class="album-details-form space-y-6" @submit.prevent="submitForm">
        <!-- Name -->
        <div>
          <label for="album-name" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">相册名称<span class="ml-1 text-primary-500">*</span></label>
          <input 
            id="album-name"
            v-model="form.name"
            type="text"
            required
            enterkeyhint="next"
            autocomplete="off"
            class="w-full min-h-12 px-4 py-3 text-base border border-gray-200 dark:border-gray-700 rounded-2xl bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 outline-none transition-all"
            placeholder="请输入相册名称"
          />
        </div>

        <!-- Description (Smart Album or User Album or Conditional Album) -->
        <div>
          <label for="album-description" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            {{ form.type === 'smart' ? '智能描述 (AI 自动匹配)' : '描述 (可选)' }}
          </label>
          <textarea 
            id="album-description"
            v-model="form.description"
            rows="4"
            class="w-full min-h-12 px-4 py-3 text-base border border-gray-200 dark:border-gray-700 rounded-2xl bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 outline-none transition-all resize-none"
            :placeholder="form.type === 'smart' ? '例如：去年夏天的海边旅行，有沙滩和大海...' : '相册描述...'"
          ></textarea>
        </div>

        <!-- Smart Album Threshold -->
        <details v-if="form.type === 'smart'" class="rounded-2xl border border-gray-200 p-4 dark:border-gray-700">
          <summary class="cursor-pointer text-sm font-medium text-gray-700 dark:text-gray-300">高级设置 · 匹配严格程度</summary>
          <div class="pt-4">
          <div class="flex justify-between items-center mb-1">
             <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">匹配阈值</label>
             <span class="text-xs text-gray-500 dark:text-gray-400">{{ (form.threshold * 100).toFixed(0) }}%</span>
          </div>
          <el-slider
            v-model="form.threshold"
            :min="0.15"
            :max="0.5"
            :step="0.01"
            :format-tooltip="(val: number) => (val * 100).toFixed(0) + '%'"
          />
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">数值越高匹配越严格，默认 25%，通常无需调整</p>
          </div>
        </details>

        <!-- Conditional Album Fields -->
        <div v-if="form.type === 'conditional'" class="space-y-4 border-t border-gray-100 dark:border-gray-800 pt-4">
            <h4 class="font-medium text-gray-900 dark:text-white">筛选条件</h4>

            <!-- Folders -->
            <div>
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">文件夹</label>
                <el-tree-select
                    v-model="form.folders"
                    size="large"
                    :props="folderTreeProps"
                    :load="loadFolderOptions"
                    :cache-data="selectedFolderCache"
                    node-key="path"
                    multiple
                    show-checkbox
                    check-strictly
                    lazy
                    filterable
                    clearable
                    collapse-tags
                    collapse-tags-tooltip
                    placeholder="选择文件夹"
                    class="w-full"
                />
                <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">包含所选文件夹及其全部子文件夹中的照片</p>
            </div>
            
            <!-- Time Range -->
            <div>
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">时间范围</label>
                <!-- Desktop Date Range -->
                <el-date-picker
                    v-if="!isMobile"
                    v-model="form.timeRange"
                    type="daterange"
                    range-separator="至"
                    start-placeholder="开始日期"
                    end-placeholder="结束日期"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    class="w-full"
                    style="width: 100%"
                />
                <!-- Mobile Date Range -->
                <div v-else class="grid min-w-0 grid-cols-1 gap-3">
                  <div class="min-w-0">
                    <label for="album-start-date" class="mb-1 block text-xs text-gray-500 dark:text-gray-400">开始日期</label>
                    <input id="album-start-date" v-model="mobileStartDate" type="date" :max="mobileEndDate || undefined" class="album-date-input" />
                  </div>
                  <div class="min-w-0">
                    <label for="album-end-date" class="mb-1 block text-xs text-gray-500 dark:text-gray-400">结束日期</label>
                    <input id="album-end-date" v-model="mobileEndDate" type="date" :min="mobileStartDate || undefined" class="album-date-input" />
                  </div>
                </div>
            </div>
            
            <!-- Locations -->
            <div>
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">地点</label>
                <el-select
                    v-model="form.locations"
                    size="large"
                    collapse-tags
                    collapse-tags-tooltip
                    multiple
                    filterable
                    remote
                    reserve-keyword
                    placeholder="请输入地点关键词搜索"
                    :remote-method="searchLocation"
                    :loading="locationLoading"
                    value-key="_id"
                    class="w-full"
                >
                    <el-option
                        v-for="item in locationOptions"
                        :key="item.label"
                        :label="item.label"
                        :value="item.value"
                    />
                </el-select>
                <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">支持搜索省、市、区</p>
            </div>

            <!-- People -->
            <div>
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">人物</label>
                <el-select
                    v-model="form.people"
                    size="large"
                    collapse-tags
                    collapse-tags-tooltip
                    multiple
                    placeholder="选择人物"
                    class="w-full"
                    filterable
                >
                    <!-- 如果为空，显示提示 -->
                    <div v-if="form.people.length === 0" class="text-xs text-gray-400 dark:text-gray-500 italic">暂无人物条件</div>
                    <!-- 否则，显示人物条件 -->
                    <el-option
                        v-for="face in faces"
                        :key="face.id"
                        :label="face.identity_name || '未知'"
                        :value="face.id"
                    />
                </el-select>
            </div>
        </div>

      </form>
      <template #footer>
        <div class="flex gap-3 sm:justify-end">
          <button 
            type="button"
            @click="closeModal"
            :disabled="loading"
            class="ts-button ts-button-secondary min-h-12 flex-1 sm:flex-none disabled:opacity-50"
          >
            取消
          </button>
          <button 
            type="submit"
            form="album-details-form"
            class="ts-button ts-button-primary min-h-12 flex-[2] sm:flex-none disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!form.name.trim() || loading"
          >
            {{ loading ? '保存中…' : isEditing ? '保存修改' : '创建相册' }}
          </button>
        </div>
      </template>
    </ResponsiveDialog>

  </div>
</template>

<script setup lang="ts">
import TicketWalletPreview from '@/views/ticket/components/TicketWalletPreview.vue'
import { memoryApi } from '@/api/memory'
import type { MemoryItem } from '@/types/memory'
import { thumbnailUrl } from '@/utils/mediaUrl'
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue';
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import { ref, reactive, onMounted, computed, type Component } from 'vue'
import { useRouter } from 'vue-router'
import { useAlbumStore } from '@/stores/albumStore'
import type { Album, FaceIdentity, CreateAlbumDto } from '@/types/album'
import { ArrowUp, ArrowDown, SlidersHorizontal, Search, MoreHorizontal, BookHeart, ChevronDown, Plus, Sparkles, Edit2, Trash2, Users, MapPin, FolderHeart, FolderOpen, Tag, Filter, History, SearchCheck, Stethoscope, WandSparkles, ChevronRight } from 'lucide-vue-next'
import { albumService, type SmartAlbumRepresentative, type SmartAlbumSection } from '@/api/album'
import { locationService } from '@/api/location'
import { faceApi } from '@/api/face'
import { ElMessage, ElMessageBox } from 'element-plus'
import { format } from 'date-fns'
import { useWindowSize } from '@vueuse/core'
import { useUiStore } from '@/stores/uiStore'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { useLongPress } from '@/composables/useLongPress'
import SmartAlbumCover from '@/components/SmartAlbumCover.vue'

const router = useRouter()
const store = useAlbumStore()
const uiStore = useUiStore()

const startTravelAlbum = () => {
  uiStore.openAgentWithPrompt('请加载 travel-album Skill，帮我自动发现最近值得整理的一段旅行。先展示少量旅行候选让我确认日期和地点；确认后挑选代表照片，生成旅行日志、个性化 HTML 和需要我确认的正式相册计划。不要替我执行相册计划。', true)
}

const startAlbumDoctor = () => {
  uiStore.openAgentWithPrompt('请加载 album-doctor Skill，对我的整个照片库做一次只读体检。按严重程度总结缺少时间、地点、AI 描述、文件指纹、未归档照片、完全重复照片和相册结构异常；只展示少量证据样本与建议。对于计数和封面问题可生成结构修复计划；对于缺失 AI 描述或文件指纹可生成带进度的后台计划；对于满足保守证据规则的缺失时间或地点，可展示逐张证据并生成可撤销计划。都先等待我表达修复意图，不要删除、移动或重命名原始照片，也不要替我确认或执行任何计划。', true)
}

const startMemoryDetective = () => {
  uiStore.openAgentWithPrompt('请加载 memory-detective Skill，作为回忆侦探帮我找回一段记不清的经历。先问我一个最有区分度的问题，引导我提供大概时间、地点、同行人、看到的文字或画面等线索；然后融合这些证据给出少量候选事件和照片，不要把推断当成事实，也不要修改任何照片。', true)
}

const { width } = useWindowSize()
const isMobile = computed(() => width.value < 768)

const formatDate = (timestamp: number) => {
  return format(new Date(timestamp), 'yyyy-MM-dd')
}

// Smart Albums Configuration
type SmartAlbumKind = 'people' | 'location' | 'classification'

interface SmartAlbumCard {
  id: SmartAlbumKind
  title: string
  description: string
  emptyDescription: string
  itemUnit: string
  icon: Component
  route: string
  data?: SmartAlbumSection | null
}

const memoryPreviews = ref<MemoryItem[]>([])
const memoryTotal = ref(0)
const memoryLoading = ref(false)
const memoryLoadError = ref(false)
const loadMemoryPreviews = async (append = false) => {
  if (memoryLoading.value) return
  memoryLoading.value = true
  memoryLoadError.value = false
  try {
    const data = await memoryApi.list('confirmed', append ? memoryPreviews.value.length : 0, 12)
    memoryPreviews.value = append ? [...memoryPreviews.value, ...data.items] : data.items
    memoryTotal.value = data.total
  } catch { memoryLoadError.value = true }
  finally { memoryLoading.value = false }
}
const collapsed = computed(() => store.collapsedSections)
const showSectionSettings = ref(false)
const sectionRank = (id: string) => store.sections.findIndex(section => section.id === id)
const visibleSmartAlbums = computed(() => smartAlbums.value.filter(group => !store.hiddenSections.includes(group.id)))
const onGroupScroll = (id: SmartAlbumKind, event: Event) => {
  const element = event.target as HTMLElement
  if (element.scrollWidth - element.scrollLeft - element.clientWidth < 180) void store.loadMoreSection(id)
}
const onMemoryScroll = (event: Event) => {
  const element = event.target as HTMLElement
  if (element.scrollWidth - element.scrollLeft - element.clientWidth < 180 && memoryPreviews.value.length < memoryTotal.value && !memoryLoading.value) void loadMemoryPreviews(true)
}
const showAlbumSearch = ref(false)
const albumSearch = ref('')
const showCreateActions = ref(false)
const showAlbumActions = ref(false)
const visibleAlbums = computed(() => store.allAlbums.filter(album => !showAlbumSearch.value || album.title.toLocaleLowerCase().includes(albumSearch.value.trim().toLocaleLowerCase())))
const createKinds = [
  { value: 'user', label: '普通相册', icon: FolderHeart },
  { value: 'conditional', label: '条件相册', icon: Filter },
  { value: 'smart', label: '智能相册', icon: Sparkles },
]
const openRepresentative = (group: SmartAlbumCard, item: SmartAlbumRepresentative) => {
  const value = group.id === 'classification' ? item.name : item.entity_id
  router.push(`${group.route}/${encodeURIComponent(value)}`)
}

const smartOverview = computed(() => store.smartAlbumOverview)
const smartOverviewLoading = ref(false)

const smartAlbums = computed<SmartAlbumCard[]>(() => [
  {
    id: 'people',
    title: '人物相册',
    description: '智能人脸识别',
    emptyDescription: '暂无人物内容',
    itemUnit: '位人物',
    icon: Users,
    route: '/album/people',
    data: smartOverview.value?.people
  },
  {
    id: 'location',
    title: '位置相册',
    description: '按地点分类',
    emptyDescription: '暂无位置内容',
    itemUnit: '个地点',
    icon: MapPin,
    route: '/album/location',
    data: smartOverview.value?.location
  },
  {
    id: 'classification',
    title: '智能分类',
    description: 'AI自动分类',
    emptyDescription: '暂无分类内容',
    itemUnit: '个分类',
    icon: Tag,
    route: '/album/classification',
    data: smartOverview.value?.classification
  }
])

const formatSmartCount = (value: number | undefined) => (value ?? 0).toLocaleString('zh-CN')

const loadSmartOverview = async () => {
  if (store.hasFreshSmartAlbumOverview()) return
  smartOverviewLoading.value = true
  try {
    await store.fetchSmartAlbumOverview()
  } catch (error) {
    console.error('Failed to load smart album overview', error)
  } finally {
    smartOverviewLoading.value = false
  }
}

const navigateToSmartAlbum = (album: any) => {
  if (album.route) {
    router.push(album.route)
  } else {
    ElMessage.info('功能开发中，敬请期待')
  }
}

const navigateToAlbum = (id: string) => {
  router.push(`/album/${id}`)
}

// Modal Logic
const showModal = ref(false)
const isEditing = ref(false)
const loading = ref(false)
const currentAlbumId = ref<string | null>(null)
const faces = ref<FaceIdentity[]>([])

interface LocationForm {
    province: string;
    city: string;
    district: string;
    _id?: string;
}

const locationOptions = ref<{ label: string; value: LocationForm }[]>([])
const locationLoading = ref(false)

interface FolderOption {
  name: string
  path: string
  isLeaf: boolean
}

const folderTreeProps = {
  label: 'name',
  children: 'children',
  isLeaf: 'isLeaf'
}

const toFolderOptions = (children: { name: string; path: string; has_children: boolean }[]): FolderOption[] =>
  children.map(folder => ({
    name: folder.name,
    path: folder.path,
    isLeaf: !folder.has_children
  }))

const loadFolderOptions = async (node: any, resolve: (options: FolderOption[]) => void) => {
  try {
    const parent = node.level === 0 ? '' : node.data.path
    const data = await albumService.getFolders(parent)
    const options = toFolderOptions(data.children || [])
    resolve(options)
  } catch (error) {
    console.error('Failed to load folders', error)
    resolve([])
  }
}

const searchLocation = async (query: string) => {
  if (query) {
    locationLoading.value = true
    try {
        const res = await locationService.searchLocations(query)
        const newOptions = res.map(item => ({
            label: item.label,
            value: {
                province: item.value.province || '',
                city: item.value.city || '',
                district: item.value.district || '',
                _id: item.label
            }
        }))
        
        // Merge with existing selected items to keep them visible
        const selectedIds = new Set(form.locations.map(l => l._id))
        const existingOptions = locationOptions.value.filter(o => selectedIds.has(o.value._id))
        
        // Filter out duplicates from new options
        const existingIds = new Set(existingOptions.map(o => o.value._id))
        const filteredNew = newOptions.filter(o => !existingIds.has(o.value._id))
        
        locationOptions.value = [...existingOptions, ...filteredNew]
    } catch (e) {
        console.error(e)
    } finally {
        locationLoading.value = false
    }
  } else {
     // Keep selected options
     const selectedIds = new Set(form.locations.map((l: any) => l._id))
     locationOptions.value = locationOptions.value.filter(o => selectedIds.has(o.value._id))
  }
}

const form = reactive({
  name: '',
  description: '',
  type: 'user', // user, smart, conditional
  timeRange: [] as string[],
  locations: [] as LocationForm[],
  people: [] as string[],
  folders: [] as string[],
  threshold: 0.25
})

const selectedFolderCache = computed(() => form.folders.map(path => ({
  name: path.split('/').filter(Boolean).pop() || path,
  path,
  isLeaf: false
})))

const albumTypeLabel = computed(() => createKinds.find(kind => kind.value === form.type)?.label || '相册')
const albumFormDescriptions: Record<string, string> = {
  user: '先给相册起个名字，创建后再添加照片',
  smart: '描述想收集的画面，AI 会自动匹配照片',
  conditional: '设置日期、地点或人物条件，自动收集符合条件的照片',
}
const albumFormDescription = computed(() => albumFormDescriptions[form.type] || '')
const mobileStartDate = computed({
  get: () => (form.timeRange[0] || '').slice(0, 10),
  set: (value: string) => {
    form.timeRange[0] = value ? `${value}T00:00:00` : ''
    if (!form.timeRange[0] && !form.timeRange[1]) form.timeRange = []
  }
})
const mobileEndDate = computed({
  get: () => (form.timeRange[1] || '').slice(0, 10),
  set: (value: string) => {
    form.timeRange[1] = value ? `${value}T23:59:59` : ''
    if (!form.timeRange[0] && !form.timeRange[1]) form.timeRange = []
  }
})

const fetchFaces = async () => {
    try {
        const data = await faceApi.listIdentities(1, 1000); // Fetch all/many faces
        // Filter out faces with no identity_name
        faces.value = data.filter((face: FaceIdentity) => face.identity_name !== '未命名');
    } catch (e) {
        console.error("Failed to fetch faces", e);
    }
}

const openCreateModal = async (type: string = 'user') => {
  isEditing.value = false
  currentAlbumId.value = null
  form.name = ''
  form.description = ''
  form.type = type
  form.timeRange = []
  form.locations = []
  locationOptions.value = []
  form.people = []
  form.folders = []
  form.threshold = 0.25
  
  if (type === 'conditional') {
      await fetchFaces()
  }
  
  showModal.value = true
}

const openEditModal = async (album: any) => {
  isEditing.value = true
  currentAlbumId.value = album.id
  form.name = album.title || album.name
  form.description = album.description || ''
  form.type = album.type || 'user'
  form.threshold = album.threshold !== undefined ? album.threshold : 0.25
  
  // Reset fields
  form.timeRange = []
  form.locations = []
  locationOptions.value = []
  form.people = []
  form.folders = []
  if (form.type === 'conditional' && album.condition) {

      await fetchFaces()
      // Populate condition fields
      if (album.condition.time_range) {
          form.timeRange = [
              album.condition.time_range.start || '',
              album.condition.time_range.end || ''
          ]
      }
      if (album.condition.locations) {
          form.locations = album.condition.locations.map((l: any) => {
             const parts = [l.province, l.city, l.district].filter(Boolean)
             const label = parts.join('')
             return {
                 province: l.province || '',
                 city: l.city || '',
                 district: l.district || '',
                 _id: label
             }
          })
          // Pre-populate options
          locationOptions.value = form.locations.map(l => ({
              label: l._id!,
              value: l
          }))
      }
      if (album.condition.people) {
          form.people = album.condition.people
      }
      if (album.condition.folders) {
          form.folders = album.condition.folders
      }
  }

  showModal.value = true
}

const closeModal = () => {
  showModal.value = false
}

const submitForm = async () => {
  if (!form.name.trim() || loading.value) return
  if (form.type === 'conditional' && form.timeRange[0] && form.timeRange[1] && form.timeRange[0] > form.timeRange[1]) {
    ElMessage.warning('结束日期不能早于开始日期')
    return
  }
  loading.value = true
  try {
    const payload: CreateAlbumDto = {
        name: form.name,
        description: form.description,
        type: form.type,
        threshold: form.type === 'smart' ? form.threshold : undefined
    }

    if (form.type === 'conditional') {
        payload.condition = {
            time_range: form.timeRange && form.timeRange.length === 2 && (form.timeRange[0] || form.timeRange[1]) ? {
                start: form.timeRange[0] || undefined,
                end: form.timeRange[1] || undefined
            } : undefined,
            locations: form.locations.filter(l => l.province || l.city || l.district).map(l => ({
                province: l.province || undefined,
                city: l.city || undefined,
                district: l.district || undefined
            })),
            people: form.people.length > 0 ? form.people : undefined,
            folders: form.folders.length > 0 ? form.folders : undefined
        }
    }

    if (isEditing.value && currentAlbumId.value) {
      await albumService.updateAlbum(currentAlbumId.value, payload)
    } else {
      await albumService.createAlbum(payload)
    }
    
    await store.fetchAlbums()
    closeModal()
    ElMessage.success(isEditing.value ? '相册更新成功' : '相册创建成功')
    // 500ms 之后再次查询数据
    setTimeout(() => {
      store.fetchAlbums()
    }, 500)
  } catch (error) {
    console.error("Operation failed", error)
    ElMessage.error("操作失败")
  } finally {
    loading.value = false
  }
}

const confirmDelete = async (album: Album) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除相册 "${album.title}" 吗？`,
      '删除相册',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    await store.deleteAlbum(album.id)
    ElMessage.success('相册已删除')
  } catch (error) {
    if (error !== 'cancel') {
      console.error("Delete failed", error)
      ElMessage.error("删除失败")
    }
  }
}

onMounted(async () => {
  await Promise.all([store.fetchAlbums(), loadSmartOverview(), loadMemoryPreviews()])
})

// ----- 移动端长按相册卡片触发的位置感知的上下文菜单 -----
interface ContextMenuPos { x: number; y: number }
const contextMenuAlbum = ref<Album | null>(null)
const menuPos = ref<ContextMenuPos>({ x: 0, y: 0 })
const showContextMenu = ref(false)
useOverlayStack(showContextMenu, () => {
  showContextMenu.value = false
  contextMenuAlbum.value = null
})

const openContextMenu = (album: Album, pos: ContextMenuPos) => {
  contextMenuAlbum.value = album
  menuPos.value = pos
  showContextMenu.value = true
}

const closeContextMenu = () => {
  showContextMenu.value = false
  contextMenuAlbum.value = null
}

const editFromContextMenu = async () => {
  const album = contextMenuAlbum.value
  closeContextMenu()
  if (album) await openEditModal(album)
}

const deleteFromContextMenu = async () => {
  const album = contextMenuAlbum.value
  closeContextMenu()
  if (album) await confirmDelete(album)
}

// useLongPress 接收 onLongPress 时一并返回触点坐标,避免闭包泄露 DOM 引用
const { onTouchstart: longPressHandler } = useLongPress({
  onLongPress: (event: TouchEvent) => {
    const album = currentAlbumForLongPress.value
    if (!album || album.type === 'system') return
    const touch = event.changedTouches?.[0]
    const pos: ContextMenuPos = touch
      ? { x: touch.clientX, y: touch.clientY }
      : menuPos.value
    openContextMenu(album, pos)
  },
})

const currentAlbumForLongPress = ref<Album | null>(null)

const onAlbumTouchStart = (album: Album, event: TouchEvent) => {
  if (!isMobile.value || album.type === 'system') return
  currentAlbumForLongPress.value = album
  longPressHandler(event)
}

</script>

<style scoped>
.album-date-input { display: block; box-sizing: border-box; width: 100%; min-width: 0; min-height: 48px; padding: 12px 16px; border: 1px solid var(--ts-color-divider); border-radius: 16px; background: var(--ts-color-surface); color: var(--ts-color-text); font-size: 16px; color-scheme: light dark; }
.album-date-input:focus-visible { outline: 2px solid var(--accent-color); outline-offset: 2px; }
.album-details-form :deep(.el-select), .album-details-form :deep(.el-tree-select) { min-width: 0; }

.album-cover-strip { display: flex; gap: 12px; overflow-x: auto; scroll-snap-type: x proximity; scroll-padding-inline: var(--ts-page-gutter); padding: 2px 2px 8px; padding-bottom: 4px; scrollbar-width: none; }
  .album-cover-strip::-webkit-scrollbar { display: none; }
  .album-cover-card { flex: 0 0 clamp(140px, 18vw, 220px); min-width: 0; scroll-snap-align: start; }
@media (max-width: 639px) {
  .album-cover-card { flex-basis: 38%; }
  .album-cover-card:active { transform: scale(.98); }
}

</style>

<template>
  <div class="ts-browse-page album-library mx-auto w-full max-w-screen-2xl px-[var(--ts-page-gutter)] pb-6">
    <!-- Header -->
    <div class="ts-browse-header album-masthead flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h1 class="journal-page-title">相册</h1>
      </div>
      <div v-glass-refraction class="ts-liquid-glass ts-glass-toolbar flex shrink-0" aria-label="相册工具栏">
        <button ref="albumSearchTrigger" class="ts-glass-button" aria-label="搜索相册" :aria-expanded="showAlbumSearch" @click="toggleAlbumSearch"><Search class="h-5 w-5" /></button>
        <div class="relative">
          <button class="ts-glass-button album-create-button" aria-label="新建相册" :aria-expanded="showCreateActions" aria-haspopup="menu" @click="showAlbumActions = false; showCreateActions = !showCreateActions"><Plus class="h-5 w-5" /></button>
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

    <div v-if="showAlbumSearch" class="album-searchbox">
      <Search aria-hidden="true" />
      <input ref="albumSearchInput" v-model="albumSearch" aria-label="相册名称" placeholder="搜索相册名称" type="search" @keydown.esc.stop="toggleAlbumSearch" />
      <button type="button" class="ts-icon-button ts-button-ghost" aria-label="关闭相册搜索" @click="toggleAlbumSearch"><X class="h-5 w-5" /></button>
    </div>

    <div class="album-sections flex flex-col gap-8">
    <section v-if="searchingAlbums || !store.hiddenSections.includes('mine')" :style="{ order: sectionRank('mine') }">
      <h2 v-if="searchingAlbums" class="album-search-heading" aria-live="polite">{{ visibleAlbums.length }} 个相册</h2>
      <h2 v-else class="mb-3 sm:mb-4">
        <button type="button" class="ts-section-title flex min-h-11 w-full items-center gap-2" :aria-expanded="!collapsed.mine" @click="collapsed.mine = !collapsed.mine">
          <ChevronDown class="h-4 w-4" :class="{ '-rotate-90': collapsed.mine }" />我的相册
        </button>
      </h2>
      <div v-show="searchingAlbums || !collapsed.mine">
        <div v-if="visibleAlbums.length" class="album-book-grid" :class="{ 'album-book-grid--search': searchingAlbums }">
          <article v-for="album in displayedAlbums" :key="album.id" class="album-book">
            <RouterLink :to="`/album/${album.id}`" class="album-book-link" :aria-label="`打开相册 ${album.title}`" @click.capture="guardAlbumClick" @touchstart.passive="onAlbumTouchStart(album, $event)">
              <div class="album-book-cover">
                <img v-if="album.cover.id && !failedAlbumCovers.has(album.cover.thumbnail)" :src="album.cover.preview || album.cover.thumbnail" alt="" loading="lazy" @error="failedAlbumCovers.add(album.cover.thumbnail)" />
                <FolderHeart v-else aria-hidden="true" class="album-book-placeholder" />
              </div>
              <div class="album-book-caption">
                <span class="album-book-type" v-if="album.type === 'smart' || album.type === 'conditional'">{{ album.type === 'smart' ? '智能相册' : '条件相册' }}</span>
                <h3>{{ album.title }}</h3>
                <span>{{ album.count.toLocaleString('zh-CN') }} 个项目</span>
              </div>
              <ArrowUpRight class="album-book-open" aria-hidden="true" />
            </RouterLink>
            <button v-if="album.type !== 'system'" type="button" class="album-book-more" :aria-label="`管理相册 ${album.title}`" @click="openContextMenu(album)">
              <MoreHorizontal aria-hidden="true" />
            </button>
          </article>
        </div>
        <div v-if="!searchingAlbums && visibleAlbums.length > collectionPreviewSize && !collectionExpanded" class="mt-3 text-center">
          <button type="button" class="ts-button ts-button-secondary" @click="collectionExpanded = true">
            显示全部 {{ visibleAlbums.length }} 个相册 <ChevronDown class="h-4 w-4" />
          </button>
        </div>
        <div v-if="!visibleAlbums.length && albumCollectionLoading" class="album-book-grid" aria-busy="true" aria-label="正在加载相册">
          <span v-for="item in 3" :key="item" class="album-book-skeleton"></span>
        </div>
        <div v-else-if="!visibleAlbums.length" class="flex flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--ts-color-border)] px-4 py-12 text-center ts-muted">
          <FolderOpen class="mb-3 h-8 w-8" aria-hidden="true" />
          <p>{{ searchingAlbums ? '没有匹配的相册' : '还没有自建相册' }}</p>
          <button v-if="!searchingAlbums" type="button" @click="openCreateModal('user')" class="ts-button ts-button-secondary mt-4">创建相册</button>
        </div>
      </div>
    </section>

    <section v-if="!searchingAlbums && !store.hiddenSections.includes('memories')" :style="{ order: sectionRank('memories') }">
      <h2 class="mb-3 flex items-center gap-2">
        <button class="ts-section-title flex min-h-11 flex-1 items-center gap-2 text-left text-gray-900 dark:text-white" :aria-expanded="!collapsed.memories" @click="collapsed.memories = !collapsed.memories"><ChevronDown class="h-4 w-4" :class="{ '-rotate-90': collapsed.memories }" />回忆</button>
        <button class="min-h-11 text-xs text-gray-500 dark:text-gray-400" aria-label="查看全部回忆" @click="router.push('/memories')">{{ memoryTotal }} <ChevronRight class="inline h-4 w-4" /></button>
      </h2>
      <div v-show="!collapsed.memories">
        <HorizontalStrip v-if="memoryPreviews.length" label="回忆" strip-class="album-cover-strip" @scroll="onMemoryScroll">
          <RouterLink v-for="memory in memoryPreviews" :key="memory.id" :to="`/memories/${memory.id}`" class="album-cover-card text-left">
            <div class="relative aspect-square overflow-hidden rounded-[22px] bg-gray-100 dark:bg-gray-800">
              <img v-if="memory.cover_photo_id" :src="thumbnailUrl(memory.cover_photo_id, 'small')" :alt="memory.title" class="h-full w-full object-cover" loading="lazy" />
              <BookHeart v-else class="absolute left-1/2 top-1/2 h-10 w-10 -translate-x-1/2 -translate-y-1/2 text-primary-500" />
            </div>
            <p class="ts-card-title mt-2 truncate text-gray-900 dark:text-white">{{ memory.title }}</p>
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ memory.photo_count }} 张照片</p>
          </RouterLink>
          <button v-if="memoryPreviews.length < memoryTotal" class="album-cover-card text-sm text-primary-500" :disabled="memoryLoading" @click="loadMemoryPreviews(true)">{{ memoryLoading ? '加载中…' : memoryLoadError ? '加载失败，点击重试' : '加载更多' }}</button>
        </HorizontalStrip>
        <div v-else class="ts-surface flex min-h-20 items-center gap-3 px-4">
          <BookHeart class="h-7 w-7 text-primary-500" /><p class="text-sm text-gray-500 dark:text-gray-400">{{ memoryLoading ? '正在加载回忆…' : memoryLoadError ? '回忆加载失败' : '确认后的记忆会显示在这里' }}</p>
          <button v-if="memoryLoadError" class="ml-auto min-h-11 text-sm text-primary-500" @click="loadMemoryPreviews()">重试</button>
        </div>
      </div>
    </section>

    <section v-if="!searchingAlbums && !store.hiddenSections.includes('tickets')" :style="{ order: sectionRank('tickets') }">
      <h2 class="mb-3 flex items-center gap-2"><button class="ts-section-title flex min-h-11 flex-1 items-center gap-2 text-left text-gray-900 dark:text-white" :aria-expanded="!collapsed.tickets" @click="collapsed.tickets = !collapsed.tickets"><ChevronDown class="h-4 w-4" :class="{ '-rotate-90': collapsed.tickets }" />票夹</button><RouterLink to="/ticket" class="min-h-11 flex items-center text-xs text-primary-600 dark:text-primary-400">查看全部</RouterLink></h2>
      <div v-show="!collapsed.tickets"><TicketWalletPreview /></div>
    </section>

    <section v-for="group in visibleSmartAlbums" :key="group.id" :style="{ order: sectionRank(group.id) }">
      <h2 class="mb-3 flex items-center gap-2">
        <button class="ts-section-title flex min-h-11 flex-1 items-center gap-2 text-left text-gray-900 dark:text-white" :aria-expanded="!collapsed[group.id]" @click="collapsed[group.id] = !collapsed[group.id]">
          <ChevronDown class="h-4 w-4" :class="{ '-rotate-90': collapsed[group.id] }" />{{ group.title }}
        </button>
        <button class="min-h-11 text-xs text-gray-500 dark:text-gray-400" :aria-label="`查看全部${group.title}`" @click="navigateToSmartAlbum(group)">{{ smartOverviewLoading ? '加载中' : formatSmartCount(group.data?.item_count) }} <ChevronRight class="inline h-4 w-4" /></button>
      </h2>
      <div v-show="!collapsed[group.id]">
      <HorizontalStrip v-if="group.data?.representatives?.length" :label="group.title" strip-class="album-cover-strip" @scroll="onGroupScroll(group.id, $event)">
        <button v-for="item in group.data.representatives" :key="item.entity_id" class="album-cover-card text-left" @click="openRepresentative(group, item)">
          <div class="relative aspect-square overflow-hidden rounded-[22px]">
            <SmartAlbumCover :type="group.id" :icon="group.icon" :data="{ item_count: 1, photo_count: item.photo_count, representatives: [item] }" :alt-prefix="item.name" />
            <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-transparent px-3 pb-3 pt-8 text-white">
              <p class="text-xs">{{ formatSmartCount(item.photo_count) }} 张</p><p class="ts-card-title truncate">{{ item.name || '未命名' }}</p>
            </div>
          </div>
        </button>
        <button v-if="group.data.representatives.length < group.data.item_count" class="album-cover-card flex items-center justify-center text-sm text-primary-500" :disabled="store.sectionLoading[group.id]" @click="store.loadMoreSection(group.id)">{{ store.sectionLoading[group.id] ? '加载中…' : store.sectionErrors[group.id] ? '加载失败，点击重试' : '加载更多' }}</button>
      </HorizontalStrip>
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
                <UnifiedDatePicker
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
                    <UnifiedDatePicker id="album-start-date" v-model="mobileStartDate" type="date" :max="mobileEndDate || undefined" class="mt-1 w-full" value-format="YYYY-MM-DD" />
                  </div>
                  <div class="min-w-0">
                    <label for="album-end-date" class="mb-1 block text-xs text-gray-500 dark:text-gray-400">结束日期</label>
                    <UnifiedDatePicker id="album-end-date" v-model="mobileEndDate" type="date" :min="mobileStartDate || undefined" class="mt-1 w-full" value-format="YYYY-MM-DD" />
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
import UnifiedDatePicker from '@/components/ui/UnifiedDatePicker.vue'
import TicketWalletPreview from '@/views/ticket/components/TicketWalletPreview.vue'
import { memoryApi } from '@/api/memory'
import type { MemoryItem } from '@/types/memory'
import { thumbnailUrl } from '@/utils/mediaUrl'
import AdaptiveMenu from '@/components/ui/AdaptiveMenu.vue';
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import { ref, reactive, onMounted, computed, nextTick, type Component } from 'vue'
import { useRouter } from 'vue-router'
import { useAlbumStore } from '@/stores/albumStore'
import type { Album, FaceIdentity, CreateAlbumDto } from '@/types/album'
import { ArrowUp, ArrowDown, ArrowUpRight, BookHeart, SlidersHorizontal, Search, MoreHorizontal, ChevronDown, Plus, Sparkles, Edit2, Trash2, Users, MapPin, FolderHeart, FolderOpen, Tag, Filter, History, SearchCheck, Stethoscope, WandSparkles, ChevronRight, X } from 'lucide-vue-next'
import { albumService, type SmartAlbumRepresentative, type SmartAlbumSection } from '@/api/album'
import { locationService } from '@/api/location'
import { faceApi } from '@/api/face'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useWindowSize } from '@vueuse/core'
import { useUiStore } from '@/stores/uiStore'
import { useOverlayStack } from '@/composables/useOverlayStack'
import { useLongPress } from '@/composables/useLongPress'
import SmartAlbumCover from '@/components/SmartAlbumCover.vue'
import HorizontalStrip from '@/components/ui/HorizontalStrip.vue'

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
const visibleSmartAlbums = computed(() => searchingAlbums.value ? [] : smartAlbums.value.filter(group => !store.hiddenSections.includes(group.id)))
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
const albumSearchInput = ref<HTMLInputElement | null>(null)
const albumSearchTrigger = ref<HTMLButtonElement | null>(null)
const albumCollectionLoading = ref(true)
const collectionExpanded = ref(false)
const collectionPreviewSize = 7
const failedAlbumCovers = ref(new Set<string>())
const searchingAlbums = computed(() => Boolean(showAlbumSearch.value && albumSearch.value.trim()))
const showCreateActions = ref(false)
const showAlbumActions = ref(false)
const visibleAlbums = computed(() => store.allAlbums.filter(album => !searchingAlbums.value || album.title.toLocaleLowerCase().includes(albumSearch.value.trim().toLocaleLowerCase())))
const displayedAlbums = computed(() => searchingAlbums.value || collectionExpanded.value
  ? visibleAlbums.value
  : visibleAlbums.value.slice(0, collectionPreviewSize))
async function toggleAlbumSearch() {
  showAlbumSearch.value = !showAlbumSearch.value
  if (!showAlbumSearch.value) albumSearch.value = ''
  await nextTick()
  if (showAlbumSearch.value) albumSearchInput.value?.focus()
  else albumSearchTrigger.value?.focus()
}
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
  get: () => (form.timeRange?.[0] || '').slice(0, 10),
  set: (value: string) => {
    form.timeRange ||= []
    form.timeRange[0] = value ? `${value}T00:00:00` : ''
    if (!form.timeRange[0] && !form.timeRange[1]) form.timeRange = []
  }
})
const mobileEndDate = computed({
  get: () => (form.timeRange?.[1] || '').slice(0, 10),
  set: (value: string) => {
    form.timeRange ||= []
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
  if (form.type === 'conditional' && form.timeRange?.[0] && form.timeRange[1] && form.timeRange[0] > form.timeRange[1]) {
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

onMounted(() => {
  void store.fetchAlbums().finally(() => { albumCollectionLoading.value = false })
  void loadSmartOverview()
  void loadMemoryPreviews()
})

const contextMenuAlbum = ref<Album | null>(null)
const showContextMenu = ref(false)
useOverlayStack(showContextMenu, () => {
  showContextMenu.value = false
  contextMenuAlbum.value = null
})

const openContextMenu = (album: Album) => {
  contextMenuAlbum.value = album
  showContextMenu.value = true
}
const guardAlbumClick = (event: MouseEvent) => {
  if (showContextMenu.value) event.preventDefault()
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

const { onTouchstart: longPressHandler } = useLongPress({
  onLongPress: () => {
    const album = currentAlbumForLongPress.value
    if (!album || album.type === 'system') return
    openContextMenu(album)
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
.album-searchbox { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; padding: 3px 5px 3px 15px; border: 1px solid var(--ts-color-border); border-radius: 999px; background: var(--ts-color-surface); }
.album-searchbox:focus-within { border-color: var(--ts-journal-focus); }
.album-searchbox > svg { width: 19px; color: var(--ts-color-text-secondary); flex-shrink: 0; }
.album-searchbox input { flex: 1; width: 0; padding-block: 8px; background: transparent; font-size: 16px; outline: none; }
.album-searchbox input::-webkit-search-cancel-button { display: none; }
.album-search-heading { margin-bottom: 12px; color: var(--ts-color-text-secondary); font-size: 14px; }
.album-book-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.album-book, .album-book-skeleton { position: relative; min-width: 0; min-height: clamp(170px, 17vw, 264px); border-radius: 18px; }
.album-book-skeleton { background: var(--ts-color-surface-muted); }
.album-book-grid:not(.album-book-grid--search) > :first-child { grid-column: span 2; }
.album-book-link { position: relative; isolation: isolate; display: flex; min-height: inherit; height: 100%; flex-direction: column; justify-content: end; overflow: hidden; border-radius: inherit; color: #f8fafc; background: #293548; }
.album-book-link::after { content: ''; position: absolute; z-index: -1; inset: 0; background: linear-gradient(180deg, rgb(2 6 23 / 30%), transparent 30%, rgb(2 6 23 / 88%) 100%); }
.album-book-cover { position: absolute; z-index: -2; inset: 0; display: grid; place-items: center; overflow: hidden; background: radial-gradient(ellipse at 70% 30%, #45556d, #1e293b 72%); }
.album-book-cover img { width: 100%; height: 100%; object-fit: cover; transition: transform 500ms cubic-bezier(.22,.61,.36,1); }
.album-book-grid:not(.album-book-grid--search) > :first-child img { object-position: center 67%; }
.album-book-placeholder { width: 42px; height: 42px; color: var(--ts-journal-on-image); stroke-width: 1; }
.album-book-link:hover img { transform: scale(1.065); }
.album-book-link:focus-visible, .album-book-more:focus-visible { outline: 2px solid var(--ts-journal-on-image); outline-offset: -3px; }
.album-book-caption { display: grid; justify-items: start; gap: 5px; padding: 16px 36px 16px 16px; }
.album-book-caption h3 { display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 2; font-family: var(--ts-journal-serif); font-size: clamp(19px, 2vw, 29px); font-weight: 700; line-height: 1.19; overflow-wrap: anywhere; }
.album-book-caption span { color: #e2e8f0; font-size: 12px; font-weight: 550; }
.album-book-caption .album-book-type { border-bottom: 1px solid var(--ts-journal-on-image); color: var(--ts-journal-on-image); padding-bottom: 3px; }
.album-book-open { position: absolute; right: 12px; bottom: 17px; width: 17px; height: 17px; }
.album-book-more { display: grid; position: absolute; top: 7px; right: 7px; width: 44px; height: 44px; place-items: center; border-radius: 50%; color: #f8fafc; background: rgb(15 23 42 / 68%); }
.album-book-more:hover { background: #1e293b; }
.album-book-more svg { width: 19px; }
.album-masthead { margin-bottom: 16px; padding-block: 24px 14px; border-bottom: 1px solid var(--ts-color-divider); }
.album-create-button { background: var(--ts-journal-action); color: white; }
.album-create-button:hover { background: var(--ts-journal-action-hover); color: white; }
.album-sections > section + section { border-top: 1px solid var(--ts-color-divider); padding-top: 14px; }
.album-sections .ts-section-title { font-size: clamp(19px, 2.1vw, 25px); font-weight: 650; letter-spacing: -.035em; }
.album-custom-cover { outline: 1px solid var(--ts-color-border); outline-offset: -1px; }
.album-cover-card:focus-visible { outline: 2px solid var(--ts-journal-focus); outline-offset: -2px; border-radius: 14px; }
.album-details-form :deep(.el-select), .album-details-form :deep(.el-tree-select) { min-width: 0; }

:deep(.album-cover-strip) { display: flex; gap: 12px; overflow-x: auto; scroll-snap-type: x proximity; scroll-padding-inline: var(--ts-page-gutter); padding: 2px 2px 8px; padding-bottom: 4px; scrollbar-width: none; }
  :deep(.album-cover-strip)::-webkit-scrollbar { display: none; }
  .album-cover-card { flex: 0 0 clamp(140px, 18vw, 220px); min-width: 0; scroll-snap-align: start; }
@media (max-width: 767px) {
  .album-book-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }
  .album-book, .album-book-skeleton { min-height: clamp(142px, 42vw, 230px); border-radius: 14px; }
  .album-book-grid:not(.album-book-grid--search) > :first-child { min-height: clamp(200px, 54vw, 310px); }
  .album-book-grid:not(.album-book-grid--search) > .album-book:nth-child(even):last-child { grid-column: span 2; }
  .album-book-caption { padding: 12px 28px 12px 12px; }
  .album-book-open { right: 9px; bottom: 14px; width: 15px; }
  .album-book-more { top: 4px; right: 4px; }
  /* Leave part of the next square cover visible to invite horizontal swiping. */
  .album-library { --album-cover-columns: 2.6; --album-cover-gap: 10px; }
  .album-library .album-masthead { margin-bottom: 10px; padding-block: 14px 8px; }
  .album-sections { gap: 16px; }
  .album-sections > section > h2 { margin-bottom: 4px; }
  .album-sections > section > h2 > :is(button, a) { position: relative; min-height: 36px; }
  .album-sections > section > h2 > :is(button, a)::after { content: ''; position: absolute; inset: -4px 0; }
  .album-sections .ts-section-title { font-size: 18px; }
  :deep(.album-cover-strip) { gap: var(--album-cover-gap); padding-bottom: 2px; }
  .album-cover-card { flex-basis: calc((100% - (var(--album-cover-columns) - 1) * var(--album-cover-gap)) / var(--album-cover-columns)); }
  .album-cover-card > div:first-child { width: 100%; border-radius: 12px; margin-bottom: 4px; }
  .album-cover-card .ts-card-title { font-size: 12px; line-height: 1.35; }
  .album-cover-card > p { margin-top: 2px; }
  .album-cover-card :deep(.absolute.inset-x-0) { padding: 16px 8px 6px; }
  .album-cover-card:active { transform: scale(.98); }
}
@media (min-width: 420px) and (max-width: 767px) {
  .album-library { --album-cover-columns: 3.4; }
}
@media (min-width: 1024px) {
  .album-book-grid:not(.album-book-grid--search):has(> .album-book:nth-child(4):last-child) { grid-template-columns: repeat(5, minmax(0, 1fr)); }
}
@media (prefers-reduced-motion: reduce) {
  .album-cover-card :deep(img), .album-cover-card > div, .album-book-cover img { transition-duration: 0s; }
}

</style>

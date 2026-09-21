<template>
  <div :class="['location-list flex flex-col relative py-6 px-4', (viewMode === 'map' || viewMode === 'trajectory' || viewMode === 'puzzle') ? 'h-full min-h-0' : 'container mx-auto', isImmersiveMap ? 'location-immersive' : '']">
    <!-- Header -->
    <div class="location-toolbar container mx-auto flex flex-col md:flex-row justify-between items-start md:items-center gap-3 md:gap-4 flex-shrink-0 z-50 transition-all duration-300 pb-2">
      <div class="location-toolbar-heading flex w-full shrink-0 items-center justify-between gap-3 md:w-auto">
        <div class="location-title-group flex shrink-0 items-center gap-2 rounded-full border border-gray-200/50 bg-white/80 px-3 py-1.5 shadow-sm backdrop-blur-md dark:border-gray-700/50 dark:bg-gray-900/80">
          <button @click="goBack" class="rounded-full bg-white p-1.5 transition-colors hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:bg-gray-900 dark:hover:bg-gray-800">
            <ArrowLeft class="w-5 h-5 text-gray-600 dark:text-gray-300" />
          </button>
          <h1 class="whitespace-nowrap text-xl font-bold text-gray-800 dark:text-white md:text-2xl">位置</h1>
        </div>
        <RouterLink to="/footprint" class="location-footprint-link flex shrink-0 items-center gap-1.5 rounded-lg bg-primary-500 px-3 py-2 text-sm text-white hover:bg-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none md:hidden" title="3D 足迹地图 · 全屏沉浸查看">
          <Globe2 class="h-4 w-4" /><span>3D 足迹</span>
        </RouterLink>
      </div>

      <div class="location-toolbar-actions flex w-full min-w-0 items-center gap-1 md:w-auto lg:gap-2">
        <RouterLink to="/footprint" class="hidden shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg bg-primary-500 px-3 py-1.5 text-sm text-white hover:bg-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none md:flex" title="3D 足迹地图 · 全屏沉浸查看">
          <Globe2 class="h-4 w-4" /><span>3D 足迹</span>
        </RouterLink>
        <!-- Add Scene Button (Left) -->
        <button
          v-if="level === 'scene'"
          @click="editingScene = null; showAddScene = true"
          class="location-add-scene flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg bg-primary-500 px-3 py-1.5 text-white shadow-sm transition-all hover:bg-primary-600"
          title="新增景区"
        >
          <Plus class="w-4 h-4" />
          <span class="hidden sm:inline">新增景区</span>
        </button>

        <!-- Year Filter -->
        <div
          ref="yearMenuRef"
          data-testid="location-year-desktop"
          class="location-year-control relative flex min-w-0 rounded-lg bg-gray-200 p-1 dark:bg-gray-800"
        >
           <button
             @click="openMobileSheet('time')"
             class="flex w-full items-center justify-center gap-1.5 whitespace-nowrap rounded-md bg-white px-3 py-1.5 text-sm font-medium text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white"
           >
             <Calendar class="hidden h-4 w-4 sm:block" />
             {{ selectedYear ? selectedYear + '年' : (isCustomRange ? '自定义范围' : '全部时间') }}
             <ChevronDown class="w-4 h-4 transition-transform duration-200" :class="{ 'rotate-180': showYearMenu }" />
           </button>

           <div
             v-show="showYearMenu"
             class="absolute top-full right-0 mt-2 hidden w-32 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden z-[60] max-h-60 overflow-y-auto lg:block"
           >
             <button
               @click="selectYear(null); showYearMenu = false"
               :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800', !selectedYear && !isCustomRange ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
             >
               全部时间
             </button>
            <button
               @click="handleCustomRangeClick"
               :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800 flex items-center justify-between', isCustomRange ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
             >
               自定义范围
             </button>
             <button
               v-for="year in availableYears"
               :key="year"
               @click="selectYear(year); showYearMenu = false"
               :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800', selectedYear === year ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
             >
               {{ year }}年
             </button>
             <div class="h-px bg-gray-200 dark:bg-gray-700 mx-2 my-1"></div>

           </div>
        </div>

        <!-- Date Range Filter -->
        <div v-if="isCustomRange" class="relative hidden rounded-lg bg-white dark:bg-gray-800 lg:flex">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            class="!w-[260px]"
            @change="handleDateRangeChange"
          />
        </div>

        <!-- Filter Toggle (Only for Scene Level) -->
        <div
          v-if="level === 'scene'"
          data-testid="location-filter-desktop"
          class="hidden rounded-lg bg-gray-200 p-1 dark:bg-gray-800 lg:flex"
        >
          <button
            v-for="opt in filterOptions"
            :key="opt.value"
            @click="filterStatus = opt.value as any"
            :class="['px-3 py-1 rounded-md text-xs font-medium transition-all bg-white dark:bg-gray-700 ', filterStatus === opt.value ? 'shadow-sm text-primary-500' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
          >
            {{ opt.label }}
          </button>
        </div>

        <!-- Level Toggle -->
        <div class="location-level-control bg-gray-200 dark:bg-gray-800 p-0 md:p-1 rounded-lg flex relative" ref="levelMenuRef">
          <!-- Mobile Dropdown Trigger -->
          <button
            @click="openMobileSheet('level')"
              class="location-level-trigger flex w-full items-center justify-center gap-1.5 whitespace-nowrap rounded-md bg-white px-3 py-1.5 text-sm font-medium text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white lg:hidden"
          >
            {{ currentLevelLabel }}
            <ChevronDown class="w-4 h-4 transition-transform duration-200" :class="{ 'rotate-180': showLevelMenu }" />
          </button>

          <!-- Mobile Dropdown Menu -->
          <div
            v-show="showLevelMenu"
            class="location-level-menu absolute left-0 top-full z-[60] mt-2 hidden max-h-[80vh] w-40 flex-col overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800"
          >
            <!-- Level Options -->
            <div class="py-1">
              <button
                v-for="opt in levelOptions"
                :key="opt.value"
                @click="changeLevel(opt.value as any); showLevelMenu = false"
                :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800', level === opt.value ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
              >
                {{ opt.label }}
              </button>
            </div>

            <div class="h-px bg-gray-200 dark:bg-gray-700 mx-2"></div>

            <!-- Year Options -->
            <div class="py-1 max-h-40 overflow-y-auto">
              <button
                @click="selectYear(null); showLevelMenu = false"
                :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800 flex items-center justify-between', !selectedYear && !isCustomRange ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
              >
                <div class="flex items-center gap-2">
                  <Calendar class="w-3.5 h-3.5 opacity-70" />
                  <span>全部时间</span>
                </div>
                <Check v-if="!selectedYear && !isCustomRange" class="w-3.5 h-3.5" />
              </button>
              <button
                @click="handleCustomRangeClick"
                :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800 flex items-center justify-between', isCustomRange ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
              >
                <span>自定义范围</span>
                <Check v-if="isCustomRange" class="w-3.5 h-3.5" />
              </button>
              <button
                v-for="year in availableYears"
                :key="year"
                @click="selectYear(year); showLevelMenu = false"
                :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors dark:bg-gray-800 flex items-center justify-between', selectedYear === year ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
              >
                <span>{{ year }}年</span>
                <Check v-if="selectedYear === year" class="w-3.5 h-3.5" />
              </button>
            </div>

            <div class="h-px bg-gray-200 dark:bg-gray-700 mx-2"></div>
            <!-- Mobile Date Range Picker -->
            <div v-if="isCustomRange" class="p-2 flex flex-col items-center gap-2">
              <el-date-picker
                v-model="dateRangeStart"
                type="date"
                placeholder="开始日期"
                value-format="YYYY-MM-DD"
                size="small"
                class="flex-1 !w-full"
              />
              <el-date-picker
                v-model="dateRangeEnd"
                type="date"
                placeholder="结束日期"
                value-format="YYYY-MM-DD"
                size="small"
                class="flex-1 !w-full"
              />
            </div>

            <!-- Mobile Filter Options -->
            <template v-if="level === 'scene'">
              <div class="h-px bg-gray-200 dark:bg-gray-700 mx-2"></div>
              <div class="py-1">
                <button
                  v-for="opt in filterOptions"
                  :key="'m-' + opt.value"
                  @click="filterStatus = opt.value as any; showLevelMenu = false"
                  :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 dark:bg-gray-800 transition-colors', filterStatus === opt.value ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
                >
                  {{ opt.label }}
                </button>
              </div>
            </template>

            <div class="h-px bg-gray-200 dark:bg-gray-700 mx-2"></div>
            
            <button
               v-show="viewMode === 'map'"
               @click="level = 'photo-map'; showLevelMenu = false"
               :class="['w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 dark:bg-gray-800 transition-colors flex items-center gap-2', level === 'photo-map' ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
            >
               <Images class="w-4 h-4" />
               地图照片
            </button>
            <button
               v-if="parentRegion"
               @click="parentRegion = undefined; fetchLocations(); showLevelMenu = false"
               class="w-full px-4 py-2 text-left text-sm hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500 transition-colors flex items-center gap-2"
            >
               <X class="w-4 h-4" />
               清除区域过滤: {{ parentRegion }}
            </button>
          </div>

          <!-- Desktop Buttons -->
          <div data-testid="location-level-desktop" class="location-level-desktop hidden lg:flex">
            <button
              @click="changeLevel('district')"
              :class="['px-4 py-1.5 rounded-md text-sm transition-all bg-white dark:bg-gray-700', level === 'district' ? ' shadow-sm text-primary-500 font-medium' : 'bg-white/60 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
            >
              区县
            </button>
            <button
              @click="changeLevel('city')"
              :class="['px-4 py-1.5 rounded-md text-sm transition-all bg-white dark:bg-gray-700', level === 'city' ? 'shadow-sm text-primary-500 font-medium' : 'bg-white/60 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
            >
              城市
            </button>
            <button
              @click="changeLevel('province')"
              :class="['px-4 py-1.5 rounded-md text-sm transition-all bg-white dark:bg-gray-700', level === 'province' ? 'shadow-sm text-primary-500 font-medium' : 'bg-white/60 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
            >
              省份
            </button>
            <button
              @click="changeLevel('scene')"
              :class="['px-4 py-1.5 rounded-md text-sm transition-all bg-white dark:bg-gray-700', level === 'scene' ? 'shadow-sm text-primary-500 font-medium' : 'bg-white/60 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
            >
              景区
            </button>
            <button
              v-if="parentRegion"
              @click="parentRegion = undefined; fetchLocations();"
              class="px-4 py-1.5 rounded-md text-sm transition-all bg-white/60 dark:bg-gray-700/60 text-gray-500 dark:text-gray-400 hover:text-primary-500 dark:hover:text-primary-400 ml-1 flex items-center gap-1"
              title="清除区域过滤"
            >
              <X class="w-3.5 h-3.5" />
              {{ parentRegion }}
            </button>
          </div>

          <div v-show="viewMode === 'map'" class="location-level-divider my-auto mx-1 hidden h-4 w-px bg-gray-300 dark:bg-gray-600 lg:block"></div>

          <button
            v-show="viewMode === 'map'"
            @click="level = 'photo-map'"
            :class="['location-photo-map-desktop hidden lg:flex px-3 py-1.5 rounded-md text-sm font-medium transition-all items-center gap-1.5 bg-white dark:bg-gray-700', level === 'photo-map' ? 'shadow-sm text-primary-500 font-medium' : 'bg-white/60 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
            title="地图照片"
          >
            <Images class="w-4 h-4" />
            <span class="hidden sm:inline">照片</span>
          </button>
        </div>
        <!-- View Toggle -->
        <div class="location-view-control relative flex rounded-lg bg-gray-200 p-0 dark:bg-gray-800 lg:p-1" ref="viewMenuRef">
          <!-- Mobile Dropdown Trigger -->
          <button
            @click="openMobileSheet('view')"
            :aria-label="`切换视图，当前${currentViewLabel}`"
            :title="currentViewLabel"
            class="location-view-trigger flex w-full items-center justify-center gap-1.5 whitespace-nowrap rounded-md bg-white px-3 py-1.5 text-sm font-medium text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white lg:hidden"
          >
            <component :is="currentViewIcon" class="h-4 w-4" />
            <span>{{ currentViewLabel }}视图</span>
            <ChevronDown class="h-4 w-4" />
          </button>

          <!-- Mobile Dropdown Menu -->
          <div
            v-show="showViewMenu"
            class="location-view-menu absolute right-0 top-full z-[60] mt-2 hidden w-36 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800"
          >
            <button
              @click="viewMode = 'grid'; showViewMenu = false"
              :class="['w-full px-4 py-2 text-left text-sm dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2', viewMode === 'grid' ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
            >
              <LayoutGrid class="w-4 h-4" />
              网格视图
            </button>
            <button
              @click="viewMode = 'map'; showViewMenu = false"
              :class="['w-full px-4 py-2 text-left text-sm dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2', viewMode === 'map' ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
            >
              <Map class="w-4 h-4" />
              地图视图
            </button>
            <button
              @click="viewMode = 'timeline'; showViewMenu = false"
              :class="['w-full px-4 py-2 text-left text-sm dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2', viewMode === 'timeline' ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
            >
              <Clock class="w-4 h-4" />
              时间轴视图
            </button>
            <button
              @click="viewMode = 'trajectory'; showViewMenu = false"
              :class="['w-full px-4 py-2 text-left text-sm dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2', viewMode === 'trajectory' ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
            >
              <Route class="w-4 h-4" />
              轨迹视图
            </button>
            <button
              @click="viewMode = 'statistics'; showViewMenu = false"
              :class="['w-full px-4 py-2 text-left text-sm dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2', viewMode === 'statistics' ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
            >
              <BarChart3 class="w-4 h-4" />
              统计视图
            </button>
            <button
              @click="viewMode = 'puzzle'; showViewMenu = false"
              :class="['w-full px-4 py-2 text-left text-sm dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2', viewMode === 'puzzle' ? 'text-primary-500 font-medium' : 'text-gray-700 dark:text-gray-200']"
            >
              <Shapes class="w-4 h-4" />
              照片拼图
            </button>
          </div>

          <!-- Desktop Buttons -->
          <div class="location-view-desktop hidden lg:flex">
            <button
              @click="viewMode = 'grid'"
              :class="['p-1.5 rounded-md transition-all bg-white dark:bg-gray-700', viewMode === 'grid' ? 'shadow-sm text-primary-500' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
              title="网格视图"
            >
              <LayoutGrid class="w-4 h-4" />
            </button>
            <button
              @click="viewMode = 'map'"
              :class="['p-1.5 rounded-md transition-all bg-white dark:bg-gray-700', viewMode === 'map' ? 'shadow-sm text-primary-500' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
              title="地图视图"
            >
              <Map class="w-4 h-4" />
            </button>
            <button
              @click="viewMode = 'timeline'"
              :class="['p-1.5 rounded-md transition-all bg-white dark:bg-gray-700', viewMode === 'timeline' ? 'shadow-sm text-primary-500' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
              title="时间轴视图"
            >
              <Clock class="w-4 h-4" />
            </button>
            <button
              @click="viewMode = 'trajectory'"
              :class="['p-1.5 rounded-md transition-all bg-white dark:bg-gray-700', viewMode === 'trajectory' ? 'shadow-sm text-primary-500' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
              title="轨迹视图"
            >
              <Route class="w-4 h-4" />
            </button>
            <button
              @click="viewMode = 'statistics'"
              :class="['p-1.5 rounded-md transition-all bg-white dark:bg-gray-700', viewMode === 'statistics' ? 'shadow-sm text-primary-500' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
              title="统计视图"
            >
              <BarChart3 class="w-4 h-4" />
            </button>
            <button
              @click="viewMode = 'puzzle'"
              :class="['p-1.5 rounded-md transition-all bg-white dark:bg-gray-700', viewMode === 'puzzle' ? 'shadow-sm text-primary-500' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200']"
              title="照片拼图"
            >
              <Shapes class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Mobile filter/action sheets: one task per sheet, shared interaction model. -->
    <Teleport to="body">
      <Transition name="mobile-sheet-fade">
        <div v-if="activeMobileSheet" class="location-sheet-layer lg:hidden" @click.self="closeMobileSheet">
          <section class="location-filter-sheet" role="dialog" aria-modal="true" :aria-label="mobileSheetTitle">
            <div class="location-filter-sheet__handle" aria-hidden="true" />
            <header class="location-filter-sheet__header">
              <h2>{{ mobileSheetTitle }}</h2>
              <button type="button" aria-label="关闭" @click="closeMobileSheet" class="location-sheet-close focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none">
                <X class="h-5 w-5" />
              </button>
            </header>

            <div v-if="activeMobileSheet === 'time'" class="location-sheet-options">
              <button type="button" :class="{ active: !selectedYear && !isCustomRange }" @click="selectYear(null)">
                <span>全部时间</span><Check v-if="!selectedYear && !isCustomRange" class="h-5 w-5" />
              </button>
              <button v-for="year in availableYears" :key="`sheet-${year}`" type="button" :class="{ active: selectedYear === year }" @click="selectYear(year)">
                <span>{{ year }}年</span><Check v-if="selectedYear === year" class="h-5 w-5" />
              </button>
              <button type="button" :class="{ active: isCustomRange }" @click="handleCustomRangeClick">
                <span class="flex items-center gap-2"><Calendar class="h-4 w-4" />自定义范围</span><Check v-if="isCustomRange" class="h-5 w-5" />
              </button>
              <div v-if="isCustomRange" class="location-sheet-dates">
                <el-date-picker v-model="dateRangeStart" type="date" placeholder="开始日期" value-format="YYYY-MM-DD" class="!w-full" />
                <el-date-picker v-model="dateRangeEnd" type="date" placeholder="结束日期" value-format="YYYY-MM-DD" class="!w-full" />
              </div>
            </div>

            <div v-else-if="activeMobileSheet === 'level'" class="location-sheet-options">
              <button v-for="opt in levelOptions" :key="`sheet-${opt.value}`" type="button" :class="{ active: level === opt.value }" @click="changeLevel(opt.value as any)">
                <span>{{ opt.label }}</span><Check v-if="level === opt.value" class="h-5 w-5" />
              </button>
              <button v-if="viewMode === 'map'" type="button" :class="{ active: level === 'photo-map' }" @click="level = 'photo-map'; fetchLocations()">
                <span>地图照片</span><Check v-if="level === 'photo-map'" class="h-5 w-5" />
              </button>
            </div>

            <div v-else class="location-view-grid">
              <button v-for="item in mobileViewOptions" :key="item.value" type="button" :class="{ active: viewMode === item.value }" @click="viewMode = item.value">
                <component :is="item.icon" class="h-6 w-6" />
                <span>{{ item.label }}</span>
                <Check v-if="viewMode === item.value" class="location-view-check h-4 w-4" />
              </button>
            </div>

            <button type="button" class="location-sheet-confirm focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" @click="closeMobileSheet">确定</button>
          </section>
        </div>
      </Transition>
    </Teleport>

    <!-- Map View -->
    <LocationMapView
      class="flex-1"
      v-show="viewMode === 'map' && level !== 'photo-map' && level !== 'scene'"
      :level="level"
      :view-mode="viewMode"
      :start-date="dateRange?.[0]"
      :end-date="dateRange?.[1]"
      :parent-region="parentRegion"
      :selected-year="selectedYear"
      :available-years="availableYears"
      @click-location="goToLocation"
      @select-year="selectYear"
      @switch-view="(mode) => viewMode = mode"
      @change-level="(level: string, viewState?: { zoom: number; center: number[]; parentRegion?: string }) => changeLevel(level as any, viewState)"
    />

    <!-- Photo Map View -->
    <LocationMap v-if="viewMode === 'map' && (level === 'photo-map' || level === 'scene')" :filter-status="filterStatus" :start-date="dateRange?.[0]" :end-date="dateRange?.[1]" class="flex-1 overflow-hidden shadow-sm" />

    <!-- Timeline View -->
    <LocationTimelineView
      v-if="viewMode === 'timeline'"
      :start-date="dateRange?.[0]"
      :end-date="dateRange?.[1]"
      :level="level"
      @click-photo="handlePhotoClick"
      class="flex-1"
    />

    <!-- Grid View -->
    <LocationListView
      v-show="viewMode === 'grid'"
      :locations="locations"
      :loading="loading"
      :level="level"
      @click="goToLocation"
      @edit="handleEdit"
      @delete="handleDelete"
    />
    <!-- Trajectory View -->
    <LocationTrajectoryView
      v-if="viewMode === 'trajectory'"
      :start-date="dateRange?.[0]"
      :end-date="dateRange?.[1]"
      :level="level"
      :view-mode="viewMode"
      @click-photo="handlePhotoClick"
      class="flex-1"
    />
    <!-- Statistics View -->
    <LocationStatsView
      v-if="viewMode === 'statistics'"
      :start-date="dateRange?.[0]"
      :end-date="dateRange?.[1]"
      :level="level"
      :parent-region="parentRegion"
      @narrow-range="handleNarrowRange"
      @go-location="goToLocation"
    />
    <!-- Puzzle View -->
    <LocationPuzzleView
      v-if="viewMode === 'puzzle'"
      :start-date="dateRange?.[0]"
      :end-date="dateRange?.[1]"
      class="flex-1"
    />
    <AddSceneDialog v-model="showAddScene" :edit-data="editingScene" @success="fetchLocations" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppBack } from '@/composables/useAppBack'
import { storeToRefs } from 'pinia'
import { useLocationStore } from '@/stores/locationStore'
import { locationService } from '@/api/location'
import type { Location, LocationStatistics, Scene } from '@/types/location'
import type { Photo } from '@/types/album'
import { ArrowLeft, LayoutGrid, Map, Images, Plus, ChevronDown, Calendar, Check, Clock, Route, BarChart3, Shapes, X, Globe2 } from 'lucide-vue-next'
import { onClickOutside } from '@vueuse/core'
import { ElMessageBox, ElMessage } from 'element-plus'
import LocationMap from './LocationMap.vue'
import AddSceneDialog from './AddSceneDialog.vue'
import LocationListView from './LocationListView.vue'
import LocationMapView from './LocationMapView.vue'
import LocationTimelineView from './LocationTimelineView.vue'
import LocationTrajectoryView from './LocationTrajectoryView.vue'
import LocationStatsView from './LocationStatsView.vue'
import LocationPuzzleView from './LocationPuzzleView.vue'
import PhotoLightbox from '@/components/PhotoLightbox.vue'

const router = useRouter()
const goBack = useAppBack('/album')
const locationStore = useLocationStore()
const { level, viewMode, filterStatus } = storeToRefs(locationStore)
const locationsRaw = ref<Location[]>([])
const statistics = ref<LocationStatistics | null>(null)
const loading = ref(true)
const showAddScene = ref(false)
const editingScene = ref<Scene | null>(null)
const showLevelMenu = ref(false)
const levelMenuRef = ref<HTMLElement | null>(null)
const showViewMenu = ref(false)
const viewMenuRef = ref<HTMLElement | null>(null)
const showYearMenu = ref(false)
const yearMenuRef = ref<HTMLElement | null>(null)
const selectedYear = ref<number | null>(null)
const availableYears = ref<number[]>([])
const dateRange = ref<[string, string] | null>(null)
const isCustomRange = ref(false)
const parentRegion = ref<string | undefined>(undefined)
const isImmersiveMap = computed(() => viewMode.value === 'map' || viewMode.value === 'trajectory')
type MobileSheet = 'time' | 'level' | 'view'
const activeMobileSheet = ref<MobileSheet | null>(null)

const mobileSheetTitle = computed(() => ({
  time: '选择时间范围',
  level: '选择地图层级',
  view: '选择视图模式'
}[activeMobileSheet.value || 'time']))

const closeMobileSheet = () => { activeMobileSheet.value = null }

const openMobileSheet = (sheet: MobileSheet) => {
  if (window.innerWidth < 1024) {
    activeMobileSheet.value = sheet
    return
  }
  if (sheet === 'time') showYearMenu.value = !showYearMenu.value
  if (sheet === 'level') showLevelMenu.value = !showLevelMenu.value
  if (sheet === 'view') showViewMenu.value = !showViewMenu.value
}

const dateRangeStart = computed({
  get: () => dateRange.value?.[0] || '',
  set: (val) => {
    if (!dateRange.value) {
      dateRange.value = [val || '', '']
    } else {
      dateRange.value[0] = val || ''
    }
    if (!dateRange.value[0] && !dateRange.value[1]) {
      dateRange.value = null
    }
    handleMobileDateChange(val, 'start')
  }
})

const dateRangeEnd = computed({
  get: () => dateRange.value?.[1] || '',
  set: (val) => {
    if (!dateRange.value) {
      dateRange.value = ['', val || '']
    } else {
      dateRange.value[1] = val || ''
    }
    if (!dateRange.value[0] && !dateRange.value[1]) {
      dateRange.value = null
    }
    handleMobileDateChange(val, 'end')
  }
})

const filterOptions = [
  { label: '全部', value: 'all' },
  { label: '已打卡', value: 'checked' },
  { label: '未打卡', value: 'unchecked' }
]

const isMobile = computed(() => {
  return window.innerWidth < 1024
})

const locations = computed(() => {
  if (level.value !== 'scene' || filterStatus.value === 'all') {
    return locationsRaw.value
  }
  return locationsRaw.value.filter(loc => {
    // Both Location and Scene might be in locationsRaw
    const count = (loc as any).count !== undefined ? (loc as any).count : (loc as any).photo_count
    if (filterStatus.value === 'checked') {
      return count > 0
    } else {
      return count === 0
    }
  })
})

onClickOutside(levelMenuRef, () => {
  showLevelMenu.value = false
})

onClickOutside(viewMenuRef, () => {
  showViewMenu.value = false
})

onClickOutside(yearMenuRef, () => {
  showYearMenu.value = false
})

const levelOptions = [
  { label: '区县', value: 'district' },
  { label: '城市', value: 'city' },
  { label: '省份', value: 'province' },
  { label: '景区', value: 'scene' }
]

const currentLevelLabel = computed(() => {
  let label = '区县'
  if (level.value === 'photo-map') {
    label = '照片'
  } else {
    const option = levelOptions.find(opt => opt.value === level.value)
    if (option) label = option.label
  }
  
  return label
})

const unlockPercentage = computed(() => {
  if (!statistics.value) return 0
  // 34 provincial administrative divisions in China
  return Math.min(Math.round((statistics.value.province_count / 34) * 100), 100)
})

const currentViewIcon = computed(() => {
  switch (viewMode.value) {
    case 'grid': return LayoutGrid
    case 'map': return Map
    case 'timeline': return Clock
    case 'trajectory': return Route
    case 'statistics': return BarChart3
    case 'puzzle': return Shapes
    default: return LayoutGrid
  }
})

const currentViewLabel = computed(() => {
  switch (viewMode.value) {
    case 'grid': return '网格'
    case 'map': return '地图'
    case 'timeline': return '时间轴'
    case 'trajectory': return '轨迹'
    case 'statistics': return '统计'
    case 'puzzle': return '拼图'
    default: return '视图'
  }
})

const mobileViewOptions = [
  { value: 'map' as const, label: '地图视图', icon: Map },
  { value: 'grid' as const, label: '网格视图', icon: LayoutGrid },
  { value: 'timeline' as const, label: '时间轴视图', icon: Clock },
  { value: 'trajectory' as const, label: '轨迹视图', icon: Route },
  { value: 'statistics' as const, label: '统计视图', icon: BarChart3 },
  { value: 'puzzle' as const, label: '照片拼图', icon: Shapes },
]

// Fetch data for Grid View
const fetchLocations = async () => {
  loading.value = true
  try {
    // Fetch stats
    statistics.value = await locationService.getStatistics()

    const startDate = dateRange.value?.[0] || undefined
    const endDate = dateRange.value?.[1] || undefined

    if (level.value === 'photo-map') {
      locationsRaw.value = await locationService.getLocations('city', 0, 10000, startDate, endDate)
      return
    }
    
    if (level.value === 'scene' && !startDate && !endDate) {
      const scenes = await locationService.getScenesList(0, 1000)
      // Map Scene to Location-like structure for the grid view
      locationsRaw.value = scenes.map(s => ({
        ...s,
        count: s.photo_count || 0,
        level: 'scene' as const
      })) as any[]
    } else if (level.value === 'scene' && (startDate || endDate)) {
      const scenes = await locationService.getScenesList(0, 1000, startDate, endDate)
      locationsRaw.value = scenes.map(s => ({
        ...s,
        count: s.photo_count || 0,
        level: 'scene' as const
      })) as any[]
    } else {
      locationsRaw.value = await locationService.getLocations(level.value, 0, 10000, startDate, endDate)
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const fetchYears = async () => {
  try {
    availableYears.value = await locationService.getYears()
  } catch (e) {
    console.error(e)
  }
}

const selectYear = (year: number | null) => {
  selectedYear.value = year
  isCustomRange.value = false
  if (year) {
    dateRange.value = [`${year}-01-01`, `${year}-12-31`]
  } else {
    dateRange.value = null
  }
  fetchLocations()
}

const handleCustomRangeClick = () => {
  isCustomRange.value = true
  selectedYear.value = null
  dateRange.value = null
  showYearMenu.value = false
  // We don't fetch locations here immediately since dateRange is empty,
  // user needs to pick a range first. But we could fetch all.
  fetchLocations()
}

const handleMobileDateChange = (val: string | null, type: 'start' | 'end') => {
  if (dateRange.value) {
    const startYear = dateRange.value[0]?.substring(0, 4) || ''
    const endYear = dateRange.value[1]?.substring(0, 4) || ''
    if (dateRange.value[0] === `${startYear}-01-01` && dateRange.value[1] === `${endYear}-12-31` && startYear === endYear && startYear) {
      selectedYear.value = parseInt(startYear)
      isCustomRange.value = false
    } else {
      selectedYear.value = null
      isCustomRange.value = true
    }
  } else {
    selectedYear.value = null
  }
  // Do not close showLevelMenu on mobile to allow selecting the other date
  if (type === 'end') {
    fetchLocations()
  } else {
    showLevelMenu.value = true
  }
}

const handleDateRangeChange = (val: [string, string] | null) => {
    const startYear = val?.[0]?.substring(0, 4) || ''
    const endYear = val?.[1]?.substring(0, 4) || ''
    if (dateRange.value) {
      if (val?.[0] === `${startYear}-01-01` && val?.[1] === `${endYear}-12-31` && startYear === endYear && startYear) {
        selectedYear.value = parseInt(startYear)
        isCustomRange.value = false
      } else {
        selectedYear.value = null
        isCustomRange.value = true
      }
  } else {
    selectedYear.value = null
    // keep isCustomRange state
  }
  showLevelMenu.value = false
  fetchLocations()
}

const handleNarrowRange = (start: string, end: string, year?: number) => {
  dateRange.value = [start, end]
  if (year) {
    selectedYear.value = year
    isCustomRange.value = false
  } else {
    const startYear = start.substring(0, 4)
    const endYear = end.substring(0, 4)
    if (start === `${startYear}-01-01` && end === `${endYear}-12-31` && startYear === endYear && startYear) {
      selectedYear.value = parseInt(startYear)
      isCustomRange.value = false
    } else {
      selectedYear.value = null
      isCustomRange.value = true
    }
  }
  showLevelMenu.value = false
  showYearMenu.value = false
  viewMode.value = 'grid'
  fetchLocations()
}

const changeLevel = (newLevel: 'city' | 'province' | 'district' | 'scene', viewState?: { zoom: number, center: number[], parentRegion?: string }) => {
  if (level.value === newLevel && !viewState?.parentRegion && !parentRegion.value) return
  level.value = newLevel
  if (viewState?.parentRegion) {
    parentRegion.value = viewState.parentRegion
  } else {
    parentRegion.value = undefined
  }
  fetchLocations()
  // Map initialization is handled by LocationMapView watcher on 'level' and 'parentRegion'
}

const goToLocation = (name: string, overrideLevel?: string, sceneId?: string) => {
  const query: any = { level: overrideLevel || level.value }
  if (sceneId) query.sceneId = sceneId
  if (dateRange.value) {
    query.startDate = dateRange.value[0]
    query.endDate = dateRange.value[1]
  }
  router.push({
    name: 'LocationDetail',
    params: { name: name },
    query
  })
}

const handleEdit = async (loc: Location) => {
  if (!loc.id) return
  try {
    const scene = await locationService.getScene(loc.id)
    editingScene.value = scene
    showAddScene.value = true
  } catch (e) {
    console.error(e)
  }
}

const handlePhotoClick = (photo: Photo, contextPhotos: Photo[]) => {
  lightboxPhotos.value = contextPhotos
  lightboxImage.value = photo
  document.body.style.overflow = 'hidden'
}

const lightboxImage = ref<Photo | null>(null)
const lightboxPhotos = ref<Photo[]>([])


const handleDelete = async (loc: Location) => {
  if (!loc.id) return
  
  try {
    await ElMessageBox.confirm(
      `确定要删除景区 "${loc.name}" 吗？此操作不可撤销。`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )
    
    loading.value = true
    await locationService.deleteScene(loc.id)
    ElMessage.success('删除成功')
    await fetchLocations()
  } catch (e: any) {
    if (e !== 'cancel') {
      console.error(e)
      ElMessage.error(e.response?.data?.detail || '删除失败')
    }
  } finally {
    loading.value = false
  }
}

// Watchers
watch(viewMode, (newMode) => {
  // Map initialization handled in LocationMapView
  if (newMode !== 'map' && level.value === 'photo-map') {
    level.value = 'city'
  }
})

onMounted(() => {
  fetchYears()
  fetchLocations()
})
</script>

<style scoped>
:global(:root) {
  --location-bg: #f8fafc;
  --location-panel: rgba(255, 255, 255, 0.96);
  --location-control: rgba(255, 255, 255, 0.9);
  --location-text: #0f172a;
  --location-muted: #64748b;
  --location-map-area: #e5eef7;
  --location-map-border: rgba(var(--theme-rgb), 0.34);
  --location-shadow: rgba(15, 23, 42, 0.12);
}

:global(html.dark) {
  --location-bg: #07111f;
  --location-panel: rgba(10, 25, 43, 0.96);
  --location-control: rgba(12, 28, 49, 0.88);
  --location-text: #dcecff;
  --location-muted: #7891aa;
  --location-map-area: #0d2238;
  --location-map-border: rgba(var(--theme-rgb), 0.34);
  --location-shadow: rgba(0, 0, 0, 0.3);
}

.location-toolbar {
  container: location-toolbar / inline-size;
}

.location-immersive {
  padding: 0;
  overflow: hidden;
  background: var(--location-bg);
  isolation: isolate;
}

.location-immersive .location-toolbar {
  position: absolute;
  inset: 0 0 auto 0;
  width: 100%;
  max-width: none;
  padding: 18px 412px 12px 24px;
  pointer-events: none;
}

.location-immersive .location-toolbar > * {
  pointer-events: auto;
}

.location-immersive .location-toolbar > div:first-child > div,
.location-immersive .location-toolbar > div:last-child > div {
  border-color: rgba(var(--theme-rgb), 0.24) !important;
  background: var(--location-control) !important;
  box-shadow: 0 12px 32px var(--location-shadow), inset 0 1px 0 rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(18px);
}

.location-immersive .location-toolbar button {
  background-color: var(--location-control) !important;
  border-color: rgba(var(--theme-rgb), 0.18) !important;
}

.location-immersive .location-toolbar h1,
.location-immersive .location-toolbar button:not(.text-primary-500) {
  color: var(--location-text);
}

@container location-toolbar (max-width: 1250px) {
  .location-immersive .location-level-desktop,
  .location-immersive .location-level-divider,
  .location-immersive .location-photo-map-desktop {
    display: none !important;
  }
  .location-immersive .location-level-trigger {
    display: flex !important;
  }
  .location-immersive .location-level-menu { display: flex; }
}

@media (max-width: 1023px) {
  .location-immersive .location-toolbar {
    padding: 12px 12px 0;
  }
}

@media (max-width: 767px) {
  .location-toolbar { gap: 8px; padding-bottom: 0; }
  .location-toolbar-heading { min-height: 52px; }
  .location-title-group {
    gap: 6px;
    padding: 0;
    border-color: transparent;
    border-radius: 0;
    background: transparent;
    box-shadow: none;
    backdrop-filter: none;
  }
  .location-immersive .location-toolbar .location-toolbar-heading .location-title-group {
    border-color: transparent !important;
    background: transparent !important;
    box-shadow: none !important;
    backdrop-filter: none;
  }
  .location-title-group button { padding: 8px; background: transparent !important; }
  .location-title-group h1 { font-size: 20px; }
  .location-footprint-link { min-height: 38px; padding: 7px 11px; border-radius: 12px; font-size: 13px; }
  .location-toolbar-actions {
    display: flex;
    gap: 8px;
  }
  .location-toolbar-actions > * {
    min-width: 0;
  }
  .location-toolbar-actions > :deep(a),
  .location-toolbar-actions button {
    min-height: 40px;
  }
  .location-year-control,
  .location-level-control { width: auto; min-width: 0; flex: 1 1 0; }
  .location-view-control { width: auto; min-width: 0; flex: 1.2 1 0; }
  .location-add-scene { width: 40px; flex: 0 0 40px; padding-inline: 0; }
  .location-year-control button,
  .location-level-trigger,
  .location-view-trigger {
    min-height: 42px;
    padding-inline: 9px;
    font-size: 12px;
    border: 1px solid rgba(var(--theme-rgb), 0.12);
    border-radius: 12px;
    box-shadow: 0 3px 10px rgba(15, 23, 42, 0.06);
  }
  .location-level-menu {
    left: 0;
    right: auto;
    width: min(240px, calc(100vw - 24px));
  }
  .location-view-menu {
    right: 0;
    width: min(180px, calc(100vw - 24px));
  }
}

.location-sheet-layer {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: calc(var(--ts-tabbar-h, 0px) + env(safe-area-inset-bottom));
  background: rgba(15, 23, 42, 0.34);
  backdrop-filter: blur(2px);
}

.location-filter-sheet {
  width: min(100%, 520px);
  max-height: min(76vh, 640px);
  overflow-y: auto;
  padding: 8px 16px 16px;
  border: 1px solid rgba(var(--theme-rgb), 0.16);
  border-radius: 22px 22px 0 0;
  color: var(--location-text);
  background: var(--location-panel);
  box-shadow: 0 -18px 50px rgba(15, 23, 42, 0.18);
}

.location-filter-sheet__handle {
  width: 40px;
  height: 5px;
  margin: 0 auto 8px;
  border-radius: 999px;
  background: #cbd5e1;
}

.location-filter-sheet__header {
  display: flex;
  min-height: 48px;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(var(--theme-rgb), 0.12);
}
.location-filter-sheet__header h2 { font-size: 17px; font-weight: 700; }
.location-sheet-close { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 10px; color: var(--location-muted); }

.location-sheet-options { padding: 8px 0; }
.location-sheet-options > button {
  display: flex;
  width: 100%;
  min-height: 48px;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  color: var(--location-text);
  font-size: 15px;
}
.location-sheet-options > button.active { color: var(--theme-primary); background: rgba(var(--theme-rgb), 0.08); }
.location-sheet-dates { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 10px 0 2px; }

.location-view-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; padding: 14px 0; }
.location-view-grid button {
  position: relative;
  display: flex;
  min-height: 86px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 13px;
  color: var(--location-text);
  background: var(--location-control);
}
.location-view-grid button.active { border-color: var(--theme-primary); color: var(--theme-primary); background: rgba(var(--theme-rgb), 0.08); }
.location-view-check { position: absolute; top: 8px; right: 8px; }
.location-sheet-confirm {
  width: 100%;
  min-height: 46px;
  border-radius: 13px;
  color: white;
  background: var(--theme-primary);
  font-size: 15px;
  font-weight: 600;
}
.mobile-sheet-fade-enter-active, .mobile-sheet-fade-leave-active { transition: opacity 180ms ease; }
.mobile-sheet-fade-enter-active .location-filter-sheet, .mobile-sheet-fade-leave-active .location-filter-sheet { transition: transform 220ms ease; }
.mobile-sheet-fade-enter-from, .mobile-sheet-fade-leave-to { opacity: 0; }
.mobile-sheet-fade-enter-from .location-filter-sheet, .mobile-sheet-fade-leave-to .location-filter-sheet { transform: translateY(100%); }
</style>

<style>
/* 全局适配 Element Plus 图片预览的深色模式，因为 el-image-viewer 是 teleport 到 body 的 */
html.dark .el-image-viewer__wrapper .el-image-viewer__btn {
  color: #e5e7eb;
  background-color: rgba(31, 41, 55, 0.6);
  border-color: rgba(75, 85, 99, 0.4);
}

html.dark .el-image-viewer__wrapper .el-image-viewer__btn:hover {
  background-color: rgba(31, 41, 55, 0.9);
}

html.dark .el-image-viewer__wrapper .el-image-viewer__mask {
  background: rgba(15, 23, 42, 0.9);
}
</style>

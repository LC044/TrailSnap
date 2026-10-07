<template>
  <div 
    class="ts-surface group max-w-md hover:shadow-md hover:border-primary-300 dark:hover:border-primary-700 transition-all duration-300 relative overflow-hidden"
  >
    <div 
      class="h-1.5 w-full opacity-80"
      :style="{ background: `linear-gradient(to right, ${currentTheme.secondary}, ${currentTheme.primary})` }"
    ></div>

    <div class="p-5">
      <div class="flex justify-between items-start mb-4">
        <div class="flex items-center gap-3">
          <div
            @click.stop="handleToggleSelect"
            :class="['w-5 h-5 rounded-full border cursor-pointer flex items-center justify-center transition-colors', isSelected ? 'bg-primary-500 border-primary-500' : 'border-slate-300 dark:border-slate-600 hover:border-primary-500']"
          >
             <Check v-if="isSelected" class="w-3 h-3 text-white" />
          </div>
          <div>
             <div class="flex items-center gap-2 text-lg font-bold text-slate-800 dark:text-slate-100">
               <span>{{ ticket.from }}</span>
               <div v-if="ticket.type === 'flight'" class="relative flex items-center justify-center w-8">
                  <Plane class="w-4 h-4 text-blue-500 transform rotate-45" />
               </div>
               <MoveRight v-else class="w-4 h-4 text-primary-500" />
               <span>{{ ticket.to }}</span>
             </div>
             <!-- 乘车人显示 -->
             <div class="text-xs text-slate-500 dark:text-slate-400 mt-1 flex items-center gap-2">
               <span>{{ ticket.type === 'flight' ? '乘机人' : '乘车人' }}：{{ ticket.name }}</span>
               <span v-if="ticket.type === 'flight'" class="px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400 text-[10px]">机票</span>
             </div>
          </div>
        </div>
        <div class="text-right">
          <div class="text-xl font-bold text-primary-600 dark:text-primary-400 font-mono">{{ ticket.trainCode }}</div>
          <div class="text-xs text-slate-400">{{ formatDate(ticket.date) }}</div>
        </div>
      </div>

      <div class="border-b border-dashed border-slate-200 dark:border-slate-600 my-3 relative">
        <div class="absolute -left-7 -top-1.5 w-3 h-3 bg-slate-50 dark:bg-slate-900 rounded-full"></div>
        <div class="absolute -right-7 -top-1.5 w-3 h-3 bg-slate-50 dark:bg-slate-900 rounded-full"></div>
      </div>

      <div class="flex justify-between items-end">
        <div class="space-y-1">
          <div class="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <Clock class="w-3.5 h-3.5" />
            <span>{{ ticket.duration }}</span>
            <span class="w-1 h-1 bg-slate-300 dark:bg-slate-600 rounded-full mx-1"></span>
            <Route class="w-3.5 h-3.5" />
            <span>{{ ticket.distance }}km</span>
            <span class="w-1 h-1 bg-slate-300 dark:bg-slate-600 rounded-full mx-1"></span>
            <span>{{ ticket.price }}元</span>
          </div>
          <div class="text-sm font-medium text-slate-600 dark:text-slate-300">
            <template v-if="ticket.type === 'flight'">
              <!-- <span class="text-xs text-slate-500">航班行程</span> -->
            </template>
            <template v-else>
              {{ ticket.seatType }} · {{ ticket.carriage }}车 {{ ticket.seatNumber }}
              <span v-if="ticket.berthType !== '无'" class="text-xs text-slate-400 ml-2">{{ ticket.berthType }}铺</span>
            </template>
          </div>
        </div>

        <!-- Desktop Buttons -->
        <div class="hidden md:flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity translate-y-2 group-hover:translate-y-0">
          <button 
            v-if="ticket.photo_id"
            @click.stop="handleViewPhoto" 
            class="ts-icon-button ts-button-ghost text-primary-600 bg-primary-50 dark:bg-slate-700 dark:text-primary-400 hover:bg-primary-500 hover:text-white"
            title="查看车票照片"
          >
            <ImageIcon class="w-4 h-4" />
          </button>
          <button 
            v-if="ticket.type === 'train'"
            @click.stop="handleViewPaper" 
            class="ts-icon-button ts-button-ghost text-orange-600 bg-orange-50 dark:bg-slate-700 dark:text-orange-400 rounded-md hover:bg-orange-500 hover:text-white dark:hover:bg-orange-600 dark:hover:text-white transition-colors"
            title="查看仿真纸质车票"
          >
            <TicketIcon class="w-4 h-4" />
          </button>
          <button @click.stop="handleEdit" class="ts-icon-button ts-button-ghost text-primary-600 bg-primary-50 dark:bg-slate-700 dark:text-primary-400 rounded-md hover:bg-primary-500 hover:text-white dark:hover:bg-primary-600 dark:hover:text-white transition-colors">
            <Pencil class="w-4 h-4" />
          </button>
          <button @click.stop="handleDelete" class="ts-icon-button ts-button-ghost text-red-500 bg-red-50 dark:bg-red-900/20 rounded-md hover:bg-red-500 hover:text-white transition-colors">
            <Trash2 class="w-4 h-4" />
          </button>
        </div>

        <!-- Mobile Dropdown -->
        <div class="md:hidden" @click.stop>
          <el-dropdown trigger="click" @command="handleCommand">
            <button class="ts-icon-button ts-button-ghost text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 bg-slate-50 dark:bg-slate-700 rounded-md">
              <MoreHorizontal class="w-5 h-5" />
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-if="ticket.photo_id" command="viewPhoto">
                  <div class="flex items-center gap-2">
                    <ImageIcon class="w-4 h-4" />
                    <span>查看车票照片</span>
                  </div>
                </el-dropdown-item>
                <el-dropdown-item v-if="ticket.type === 'train'" command="viewPaper">
                  <div class="flex items-center gap-2">
                    <TicketIcon class="w-4 h-4" />
                    <span>查看仿真车票</span>
                  </div>
                </el-dropdown-item>
                <el-dropdown-item command="edit">
                  <div class="flex items-center gap-2">
                    <Pencil class="w-4 h-4" />
                    <span>编辑</span>
                  </div>
                </el-dropdown-item>
                <el-dropdown-item command="delete">
                  <div class="flex items-center gap-2 text-red-500">
                    <Trash2 class="w-4 h-4" />
                    <span>删除</span>
                  </div>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </div>
    <div v-if="ticket.comments" class="bg-slate-50 dark:bg-slate-700/30 px-5 py-2 text-xs text-slate-500 dark:text-slate-400 border-t border-slate-200 dark:border-slate-700">
      <span class="font-medium text-slate-700 dark:text-slate-300">备注：</span>{{ ticket.comments }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { MoveRight, Clock, Route, Pencil, Trash2, Check, Plane, Ticket as TicketIcon, MoreHorizontal, Image as ImageIcon } from 'lucide-vue-next';

const props = defineProps({
  // 车票数据
  ticket: {
    type: Object,
    required: true,
    default: () => ({})
  },
  // 选中的车票ID数组
  selectedTicketIds: {
    type: Array,
    required: true,
    default: () => []
  },
  // 当前主题
  currentTheme: {
    type: Object,
    required: true,
    default: () => ({ primary: '#3b82f6', secondary: '#60a5fa' })
  }
});

const emit = defineEmits(['toggle-select', 'edit', 'delete', 'view-paper', 'view-photo']);

// 计算属性：当前车票是否被选中
const isSelected = computed(() => {
  return props.selectedTicketIds.includes(props.ticket.id);
});

// 日期格式化（只显示日期部分）
const formatDate = (dateStr) => {
  const date = new Date(dateStr);
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  });
};

// 处理切换选中状态
const handleToggleSelect = () => {
  emit('toggle-select', props.ticket.id);
};

// 处理编辑
const handleEdit = () => {
  emit('edit', props.ticket);
};

// 处理删除
const handleDelete = () => {
  emit('delete', props.ticket.id);
};

// 处理查看纸质票
const handleViewPaper = () => {
  emit('view-paper', props.ticket);
};

// 处理查看照片
const handleViewPhoto = () => {
  emit('view-photo', props.ticket);
};

// 处理下拉菜单命令
const handleCommand = (command) => {
  switch (command) {
    case 'viewPhoto':
      handleViewPhoto();
      break;
    case 'viewPaper':
      handleViewPaper();
      break;
    case 'edit':
      handleEdit();
      break;
    case 'delete':
      handleDelete();
      break;
  }
};
</script>

<style scoped>
/* 保持原有的卡片样式，如需修改可在此添加 */
</style>
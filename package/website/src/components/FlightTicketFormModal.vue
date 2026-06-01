<!-- src/components/FlightTicketFormModal.vue -->
<template>
  <Transition name="fade">
    <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" @click="handleCancel"></div>
      <div class="bg-white dark:bg-slate-800 rounded-2xl shadow-xl w-full max-w-2xl relative z-10 overflow-hidden flex flex-col max-h-[90vh]">
        <div class="px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex justify-between items-center bg-slate-50 dark:bg-slate-800">
          <h2 class="text-lg font-bold text-slate-800 dark:text-white">{{ isEditing ? '编辑飞机票' : '新增飞机票' }}</h2>
          <div class="flex items-center gap-2">
             <button 
              @click="triggerFileInput"
              :disabled="recognizing"
              class="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400 rounded-md hover:bg-indigo-100 dark:hover:bg-indigo-900/50 transition-colors"
              title="上传机票图片自动识别"
            >
              <Sparkles v-if="!recognizing" class="w-4 h-4" />
              <span v-else class="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></span>
              {{ recognizing ? '识别中...' : '智能填充' }}
            </button>
            <input 
              ref="fileInput"
              type="file" 
              accept="image/*" 
              class="hidden" 
              @change="handleFileChange"
            />
            <button @click="handleCancel" class="text-slate-400 hover:text-red-500 transition-colors ml-2 dark:bg-slate-700 dark:text-slate-200">
              <X class="w-6 h-6" />
            </button>
          </div>
        </div>
        <div class="p-6 overflow-y-auto dark:text-slate-200">
          <form @submit.prevent="handleSubmit" class="grid grid-cols-1 md:grid-cols-2 gap-2">
            <!-- 航班号 -->
            <div class="space-y-1 md:col-span-2">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">航班号 <span class="text-red-500">*</span></label>
              <input 
                v-model="form.flight_code" 
                type="text" 
                required 
                class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none font-mono"
                placeholder="如：MU2393" 
              />
            </div>

            <!-- 出发地 -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">出发地 <span class="text-red-500">*</span></label>
              <input 
                v-model="form.from" 
                type="text" 
                required 
                class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition-colors"
                placeholder="如：北京首都" 
              />
            </div>

            <!-- 目的地 -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">目的地 <span class="text-red-500">*</span></label>
              <input 
                v-model="form.to" 
                type="text" 
                required 
                class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition-colors"
                placeholder="如：上海虹桥" 
              />
            </div>

            <!-- 乘车人 -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">乘车人 <span class="text-red-500">*</span></label>
              <input v-model="form.name" type="text" required class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition-colors" placeholder="如：张三" />
            </div>

            <!-- 出发日期时间 -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">出发日期时间 <span class="text-red-500">*</span></label>
              <input 
                v-model="form.dateTime" 
                type="datetime-local" 
                required 
                class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
              />
            </div>

            <!-- 价格 -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">票价（元）<span class="text-red-500">*</span></label>
              <input v-model.number="form.price" type="number" step="0.01" min="0" required class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none" placeholder="1098" />
            </div>

            <!-- 里程 -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">里程 (km)
              </label>
              <input
                v-model.number="form.distance"
                type="number"
                min="0"
                class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                placeholder="1200"
              />
            </div>

            <!-- 运行时间 -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">运行时间（分钟）
              </label>
              <input 
                v-model.number="form.totalRunningTime" 
                type="number" 
                min="0" 
                class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                placeholder="150" 
              />
            </div>

            <!-- 备注 -->
            <div class="md:col-span-2 space-y-1">
               <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">备注</label>
               <textarea v-model="form.comments" rows="2" class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none resize-none" placeholder="旅行的意义..."></textarea>
            </div>
          </form>
        </div>

        <div class="px-6 py-4 border-t border-slate-200 dark:border-slate-700 flex justify-end gap-3 bg-slate-50 dark:bg-slate-800">
          <button @click="handleCancel" class="px-5 py-2 text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-600 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors dark:bg-slate-700 dark:text-slate-200">取消</button>
          <button
            @click="handleSubmit"
            :disabled="saving"
            :class="['px-5 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 shadow-md shadow-primary-200 dark:shadow-none transition-transform active:scale-95', saving ? 'opacity-70 cursor-not-allowed' : '']"
          >
            <span v-if="saving" class="inline-block w-4 h-4 mr-2 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
            保存
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, watch } from 'vue';
import { X, Sparkles } from 'lucide-vue-next';
import axios from 'axios';
import { ElMessage } from 'element-plus';

// 接收props
const props = defineProps({
  isOpen: {
    type: Boolean,
    required: true,
    default: false
  },
  isEditing: {
    type: Boolean,
    required: true,
    default: false
  },
  initialData: {
    type: Object,
    default: () => ({})
  },
  currentTheme: {
    type: Object,
    required: true
  },
  saving: {
    type: Boolean,
    required: true,
    default: false
  },
  apiBaseUrl: { 
    type: String,
    required: true,
    default: 'http://localhost:8000'
  }
});

// 定义emit事件
const emit = defineEmits(['save', 'cancel']);

// 创建axios实例
const axiosInstance = axios.create({
  baseURL: props.apiBaseUrl,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 识别相关
const fileInput = ref(null);
const recognizing = ref(false);

const triggerFileInput = () => {
  fileInput.value.click();
};

const handleFileChange = async (event) => {
  const file = event.target.files[0];
  if (!file) return;

  // Reset input
  event.target.value = '';

  recognizing.value = true;
  try {
    const formData = new FormData();
    formData.append('file', file);
    
    // 调用飞机票识别接口
    const response = await axiosInstance.post('/flight-ticket/recognize', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
    
    const data = response.data;
    
    // 填充表单
    if (data.flight_code) form.value.flight_code = data.flight_code;
    if (data.departure_city) form.value.from = data.departure_city;
    if (data.arrival_city) form.value.to = data.arrival_city;
    if (data.datetime) form.value.dateTime = data.datetime.replace(' ', 'T').slice(0, 16);
    if (data.price) form.value.price = data.price;
    if (data.name) form.value.name = data.name;
    
    ElMessage.success('机票识别成功，已自动填充');
    
  } catch (error) {
    console.error('Recognition failed:', error);
    ElMessage.error(error.response?.data?.detail || '识别失败，请重试');
  } finally {
    recognizing.value = false;
  }
};

// 表单模型
const form = ref({
  id: null,
  flight_code: '',
  from: '', 
  to: '', 
  name: '', 
  dateTime: new Date().toISOString().slice(0, 16),
  price: 0,
  totalRunningTime: 0, 
  distance: 0, 
  comments: ''
});

// 重置表单
const resetForm = () => {
  form.value = {
    id: null,
    flight_code: '',
    from: '',
    to: '',
    name: '',
    dateTime: new Date().toISOString().slice(0, 16),
    price: 0,
    totalRunningTime: 0,
    distance: 0,
    comments: ''
  };
};

// 处理提交
const handleSubmit = () => {
  // 表单验证
  if (!form.value.name) {
    ElMessage.error('乘车人姓名不能为空');
    return;
  }
  if (!form.value.flight_code) {
    ElMessage.error('航班号不能为空');
    return;
  }
  
  // 格式化表单数据
  const submitData = {
    id: form.value.id,
    flight_code: form.value.flight_code,
    departure_city: form.value.from,
    arrival_city: form.value.to,
    name: form.value.name,
    date_time: form.value.dateTime.replace('T', ' '),
    price: form.value.price,
    total_running_time: form.value.totalRunningTime,
    total_mileage: form.value.distance,
    comments: form.value.comments
  };
  
  emit('save', submitData);
};

// 处理取消
const handleCancel = () => {
  emit('cancel');
};

// 监听initialData变化，更新表单
watch(
  () => props.initialData,
  (newVal) => {
    if (newVal && props.isEditing) {
      form.value = {
        id: newVal.id,
        flight_code: newVal.flight_code || '',
        from: newVal.departure_city || '',
        to: newVal.arrival_city || '',
        name: newVal.name || '',
        dateTime: newVal.date_time ? newVal.date_time.replace(' ', 'T').slice(0, 16) : new Date().toISOString().slice(0, 16),
        price: newVal.price || 0,
        totalRunningTime: newVal.total_running_time || 0,
        distance: newVal.total_mileage || 0,
        comments: newVal.comments || ''
      };
    } else if (!props.isEditing) {
      resetForm();
    }
  },
  { immediate: true, deep: true }
);

</script>

<style scoped>
/* 过渡动画 */
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}

/* 候选项 hover 效果优化 */
::-webkit-scrollbar {
  width: 4px;
  height: 4px;
}
::-webkit-scrollbar-thumb {
  background-color: #cbd5e1;
  border-radius: 2px;
}
.dark ::-webkit-scrollbar-thumb {
  background-color: #475569;
}
</style>

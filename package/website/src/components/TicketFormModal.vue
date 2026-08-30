<!-- src/components/TicketFormModal.vue -->
<template>
  <Transition name="fade">
    <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" @click="handleCancel"></div>
      <div class="bg-white dark:bg-slate-800 rounded-2xl shadow-xl w-full max-w-2xl relative z-10 overflow-hidden flex flex-col max-h-[90vh]">
        <div class="px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex justify-between items-center bg-slate-50 dark:bg-slate-800">
          <h2 class="text-lg font-bold text-slate-800 dark:text-white">{{ isEditing ? '编辑车票' : '新增车票' }}</h2>
          <div class="flex items-center gap-2">
             <button 
              @click="triggerFileInput"
              :disabled="recognizing"
              class="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400 rounded-md hover:bg-indigo-100 dark:hover:bg-indigo-900/50 transition-colors"
              title="上传车票图片自动识别"
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
            <!-- 车次（移到第一个位置） -->
            <div class="space-y-1 md:col-span-2">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">车次 <span class="text-red-500">*</span></label>
              <div class="relative">
                <input 
                  v-model="form.train_code" 
                  type="text" 
                  required 
                  class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none font-mono"
                  placeholder="G101 / Z123" 
                  @input="debouncedFetchSchedules"
                  @blur="fetchSchedules"
                />
                <span v-if="fetchingSchedules" class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs">
                  查询中...
                </span>
              </div>
              <p v-if="scheduleError" class="text-xs text-red-500 mt-1">{{ scheduleError }}</p>
            </div>

            <!-- 出发地（带候选项） -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">出发地 <span class="text-red-500">*</span></label>
              <input 
                v-model="form.from" 
                type="text" 
                required 
                class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition-colors"
                placeholder="如：北京南" 
              />
              <!-- 出发地候选项 -->
              <div v-if="stationOptions.length > 0" class="mt-1 max-h-40 overflow-y-auto bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-md shadow-sm z-10">
                <div 
                  v-for="station in stationOptions" 
                  :key="station.station_telecode"
                  @click="selectStation('from', station)"
                  class="px-3 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-600 cursor-pointer transition-colors"
                >
                  {{ station.station_name }}
                  <span class="text-xs text-slate-400 ml-2">{{ station.station_telecode }}</span>
                </div>
              </div>
            </div>

            <!-- 目的地（带候选项） -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">目的地 <span class="text-red-500">*</span></label>
              <input 
                v-model="form.to" 
                type="text" 
                required 
                class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition-colors"
                placeholder="如：上海虹桥" 
              />
              <!-- 目的地候选项 -->
              <div v-if="stationOptions.length > 0" class="mt-1 max-h-40 overflow-y-auto bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-md shadow-sm z-10">
                <div 
                  v-for="station in stationOptions" 
                  :key="station.station_telecode"
                  @click="selectStation('to', station)"
                  class="px-3 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-600 cursor-pointer transition-colors"
                >
                  {{ station.station_name }}
                  <span class="text-xs text-slate-400 ml-2">{{ station.station_telecode }}</span>
                </div>
              </div>
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

            <!-- 座位信息 -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">座位类型 <span class="text-red-500">*</span></label>
              <select v-model="form.seatType" required class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none">
                <option>二等座</option>
                <option>一等座</option>
                <option>商务座</option>
                <option>硬卧</option>
                <option>软卧</option>
                <option>硬座</option>
                <option>软座</option>
                <option>无座</option>
              </select>
            </div>
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">铺位类型</label>
              <select v-model="form.berthType" class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none">
                <option>无</option>
                <option>上铺</option>
                <option>中铺</option>
                <option>下铺</option>
              </select>
            </div>

            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">车厢号 <span class="text-red-500">*</span></label>
              <input v-model="form.carriage" type="text" required class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none" placeholder="如：03 / 8A" />
            </div>
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">座位号 <span class="text-red-500">*</span></label>
              <input v-model="form.seatNumber" type="text" :required="form.seatType !== '无座'" :disabled="form.seatType === '无座'" class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none" placeholder="如：12A / 05下" />
            </div>

            <!-- 价格和里程（自动计算后可编辑） -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">票价（元）<span class="text-red-500">*</span></label>
              <input v-model.number="form.price" type="number" step="0.01" min="0" required class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none" placeholder="198.5" />
            </div>
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">里程 (km)
              </label>
              <input
                v-model.number="form.distance"
                type="number"
                min="0"
                class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                placeholder="1318"
              />
            </div>

            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">运行时间（分钟）
              </label>
              <input 
                v-model.number="form.totalRunningTime" 
                type="number" 
                min="0" 
                class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                placeholder="268" 
              />
            </div>
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">优惠类型</label>
              <select v-model="form.discountType" class="w-full p-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none">
                <option>全价票</option>
                <option>学生票</option>
                <option>儿童票</option>
                <option>优惠票</option>
              </select>
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
import { ref, watch, onUnmounted } from 'vue';
import { X } from 'lucide-vue-next';
import axios from 'axios';
import { toServerUrl } from '@/config/server';
import { ElMessage } from 'element-plus';
import { ticketService } from '@/api/ticketService';


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
  apiBaseUrl: { // 新增：接收API基础地址
    type: String,
    required: false,
    default: () => toServerUrl('/api')
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
    const data = await ticketService.recognizeTicket(file);
    // 重置被识别字段，避免历史残留
    form.value.train_code = '';
    form.value.from = '';
    form.value.to = '';
    form.value.dateTime = new Date().toISOString().slice(0, 16);
    form.value.carriage = '';
    form.value.seatNumber = '';
    form.value.berthType = '无';
    form.value.price = 0;
    form.value.seatType = '二等座';
    form.value.name = '';
    
    // 填充表单
    if (data.train_code) form.value.train_code = data.train_code;
    if (data.departure_station) form.value.from = data.departure_station;
    if (data.arrival_station) form.value.to = data.arrival_station;
    if (data.datetime) form.value.dateTime = data.datetime;
    if (data.carriage) form.value.carriage = data.carriage;
    if (data.seat_num) form.value.seatNumber = data.seat_num;
    if (data.price) form.value.price = data.price;
    if (data.seat_type) form.value.seatType = data.seat_type;
    if (data.name) form.value.name = data.name;
    if (data.berth_type) form.value.berthType = data.berth_type;
    if (data.discount_type) form.value.discountType = data.discount_type;
    // 互斥规则：无座 → seatNumber 清空
    if (data.seat_type === '无座') {
      form.value.seatNumber = '';
    }
    
    ElMessage.success('车票识别成功，已自动填充');
    
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
  train_code: '', // 车次（移到第一个）
  from: '', // 出发地
  to: '', // 目的地
  name: '', // 乘车人
  dateTime: new Date().toISOString().slice(0, 16),
  carriage: '',
  seatNumber: '',
  berthType: '无',
  price: 0,
  seatType: '二等座',
  discountType: '全价票',
  totalRunningTime: 0, // 运行时间（分钟）
  distance: 0, // 里程（km）
  comments: ''
});

// 新增：时刻表相关状态
const schedules = ref([]); // 完整时刻表数据
const stationOptions = ref([]); // 车站候选项（去重）
const fetchingSchedules = ref(false); // 查询中状态
const scheduleError = ref(''); // 查询错误信息
const autoCalculated = ref(false); // 是否自动计算了里程和时间

// 防抖函数（优化车次查询）
const debounce = (fn, delay = 500) => {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
};
const debouncedFetchSchedules = debounce(fetchSchedules);

// 重置表单
const resetForm = () => {
  form.value = {
    id: null,
    train_code: '',
    from: '',
    to: '',
    name: '',
    dateTime: new Date().toISOString().slice(0, 16),
    carriage: '',
    seatNumber: '',
    berthType: '无',
    price: 0,
    seatType: '二等座',
    discountType: '全价票',
    totalRunningTime: 0,
    distance: 0,
    comments: ''
  };
  resetScheduleRelated();
};

// 重置时刻表相关状态
const resetScheduleRelated = () => {
  schedules.value = [];
  stationOptions.value = [];
  scheduleError.value = '';
  autoCalculated.value = false;
};

// 查询时刻表
async function fetchSchedules() {
  const trainCode = form.value.train_code.trim();
  if (!trainCode) {
    resetScheduleRelated();
    return;
  }

  fetchingSchedules.value = true;
  scheduleError.value = '';
  try {
    // 只传递train_code，其他参数留空
    const response = await axiosInstance.get('/railway/train-schedules', {
      params: {
        train_code: trainCode,
        page: 1,
        page_size: 100 // 一次获取更多车站
      }
    });

    const { data } = response.data;
    if (data?.list && data.list.length > 0) {
      schedules.value = data.list;
      // 提取去重的车站选项
      const uniqueStations = Array.from(
        new Map(data.list.map(station => [station.station_telecode, station])).values()
      ).sort((a, b) => a.sequence - b.sequence);
      stationOptions.value = uniqueStations;
    } else {
      stationOptions.value = [];
      scheduleError.value = '未查询到该车次的时刻表信息';
    }
  } catch (err) {
    scheduleError.value = '查询时刻表失败，请重试';
    console.error('Fetch train schedules error:', err);
  } finally {
    fetchingSchedules.value = false;
  }
}

// 选择车站
const selectStation = (type, station) => {
  form.value[type] = station.station_name;
  // 选择后自动计算（如果两个字段都已选择）
  if (form.value.from && form.value.to) {
    calculateDistanceAndTime(form.value.from, form.value.to);
  }
};

// 自动计算里程和运行时间
const calculateDistanceAndTime = (fromStation, toStation) => {
  // 找到出发站和到达站的记录
  const fromRecord = schedules.value.find(
    item => item.station_name === fromStation
  );
  const toRecord = schedules.value.find(
    item => item.station_name === toStation
  );

  if (fromRecord && toRecord) {
    // 确保出发站序号小于到达站序号
    if (fromRecord.sequence < toRecord.sequence) {
      // 里程 = 到达站累计里程 - 出发站累计里程
      form.value.distance = Math.max(0, toRecord.accumulated_mileage - fromRecord.accumulated_mileage);
      // 运行时间 = 到达站运行时间 - 出发站运行时间
      form.value.totalRunningTime = Math.max(0, toRecord.running_time - fromRecord.running_time);
      autoCalculated.value = true;
    } else {
      autoCalculated.value = false;
      scheduleError.value = '出发站序号不能大于到达站';
    }
  } else {
    autoCalculated.value = false;
  }
};

// 处理提交
const handleSubmit = () => {
  // 表单验证
  if (!form.value.name) {
    ElMessage.error('乘车人姓名不能为空');
    //
    // alert('乘车人姓名不能为空');
    return;
  }
  
  // 格式化表单数据（转换日期格式）
  const submitData = {
    ...form.value,
    dateTime: form.value.dateTime.replace('T', ' ') // 转换为后端需要的格式
  };
  
  emit('save', submitData);
};

// 处理取消
const handleCancel = () => {
  emit('cancel');
};

// 组件卸载时清除防抖定时器
onUnmounted(() => {
  debouncedFetchSchedules.cancel?.();
});

// 监听initialData变化，更新表单
watch(
  () => props.initialData,
  (newVal) => {
    if (newVal && props.isEditing) {
      form.value = {
        id: newVal.id,
        train_code: newVal.train_code || '',
        from: newVal.from || '',
        to: newVal.to || '',
        name: newVal.name || '',
        dateTime: newVal.dateTime ? newVal.dateTime.replace(' ', 'T').slice(0, 16) : new Date().toISOString().slice(0, 16),
        carriage: newVal.carriage || '',
        seatNumber: newVal.seatNumber || '',
        berthType: newVal.berthType || '无',
        price: newVal.price || 0,
        seatType: newVal.seatType || '二等座',
        discountType: newVal.discountType || '全价票',
        totalRunningTime: newVal.totalRunningTime || 0,
        distance: newVal.distance || 0,
        comments: newVal.comments || ''
      };
      // 如果是编辑模式且有车次，自动查询时刻表
      if (form.value.train_code) {
        fetchSchedules();
      }
    } else if (!props.isEditing) {
      // 重置表单
      resetForm();
    }
  },
  { immediate: true, deep: true }
);

// 监听车次变化，清空之前的车站选项和计算结果
watch(
  () => form.value.train_code,
  (newVal, oldVal) => {
    if (newVal !== oldVal && !newVal) {
      resetScheduleRelated();
    }
  }
);

// 监听出发地和目的地变化，自动计算里程和时间
watch(
  () => [form.value.from, form.value.to],
  ([newFrom, newTo]) => {
    if (newFrom && newTo && schedules.value.length > 0) {
      calculateDistanceAndTime(newFrom, newTo);
    }
  },
  { deep: true }
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

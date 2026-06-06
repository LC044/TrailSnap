<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-900 p-4 sm:p-6 transition-colors duration-300">
    <!-- 页面标题 -->
    <h1 class="text-[clamp(1.5rem,5vw,2.5rem)] font-bold text-gray-800 dark:text-gray-100 mb-6 text-center">
      车票信息编辑
    </h1>
    <!-- 主要内容区域：桌面端左右布局，移动端上下布局 -->
    <div class="max-w-6xl mx-auto">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
        <!-- 表单编辑区：桌面端在左侧 -->
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-6 transition-colors duration-300">
          <form @submit.prevent="handleSaveImage" class="space-y-5">
            <!-- 1. 出发/到达信息 -->
            <div class="border-b border-gray-200 dark:border-gray-700 pb-4">
              <h3 class="text-lg font-semibold text-gray-700 dark:text-gray-200 mb-3 flex items-center">
                <span class="w-6 h-6 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 rounded-full flex items-center justify-center mr-2 text-sm">
                  🚄
                </span>
                出发/到达
              </h3>
              <!-- 移动端单列，平板以上双列 -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">出发站</label>
                  <input 
                    v-model="form.fromStation" 
                    type="text" 
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：上海虹桥"
                    required
                  >
                </div>
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">出发站拼音</label>
                  <input 
                    v-model="form.fromPinyin" 
                    type="text" 
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：shanghaihongqiao"
                    pattern="[a-z]+"
                    title="仅允许小写字母"
                    required
                  >
                </div>
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">到达站</label>
                  <input
                    v-model="form.toStation"
                    type="text"
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：南京南"
                    required
                  >
                </div>
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">到达站拼音</label>
                  <input
                    v-model="form.toPinyin"
                    type="text"
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：nanjingnan"
                    pattern="[a-z]+"
                    title="仅允许小写字母"
                    required
                  >
                </div>
              </div>
            </div>

            <!-- 2. 车次/时间信息 -->
            <div class="border-b border-gray-200 dark:border-gray-700 pb-4">
              <h3 class="text-lg font-semibold text-gray-700 dark:text-gray-200 mb-3 flex items-center">
                <span class="w-6 h-6 bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 rounded-full flex items-center justify-center mr-2 text-sm">
                  🕒
                </span>
                车次/时间
              </h3>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">车次</label>
                  <input
                    v-model="form.trainCode"
                    type="text"
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：G2025"
                    pattern="[GDKZT][0-9]+"
                    title="以G/D/K/Z/T开头，后接数字"
                    required
                  >
                </div>
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">日期时间</label>
                  <input
                    v-model="form.dateTime"
                    type="datetime-local"
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    @change="formatDateTime"
                    required
                  >
                  <p class="text-xs text-gray-500 dark:text-gray-400 mt-1"></p>
                </div>
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">检票口</label>
                  <input 
                    v-model="form.gate" 
                    type="text" 
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：5A"
                    pattern="[0-9]+[A-Za-z]"
                    title="数字+字母格式，例5A、12B"
                    required
                  >
                </div>
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">座位类型</label>
                  <select 
                    v-model="form.seatType" 
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all appearance-none"
                    required
                  >
                    <option value="一等座">一等座</option>
                    <option value="二等座">二等座</option>
                    <option value="商务座">商务座</option>
                    <option value="无座">无座</option>
                    <!-- 新增卧铺类型 -->
                    <option value="硬座">硬座</option>
                    <option value="软座">软座</option>
                    <option value="特等座">特等座</option>
                    <option value="软卧">软卧</option>
                    <option value="硬卧">硬卧</option>
                    <option value="动卧">动卧</option>
                    <option value="高级软卧">高级软卧</option>
                    <option value="一等卧">一等卧</option>
                    <option value="二等卧">二等卧</option>
                  </select>
                </div>
              </div>
            </div>

            <!-- 3. 座位/价格信息 -->
            <div class="border-b border-gray-200 dark:border-gray-700 pb-4">
              <h3 class="text-lg font-semibold text-gray-700 dark:text-gray-200 mb-3 flex items-center">
                <span class="w-6 h-6 bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 rounded-full flex items-center justify-center mr-2 text-sm">
                  💺
                </span>
                座位/价格
              </h3>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">车厢号</label>
                  <input 
                    v-model="form.carriage" 
                    type="text" 
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：07"
                    pattern="[0-9]{1,2}"
                    title="1-2位数字，例7、12"
                    required
                  >
                </div>
                <!-- 铺位类型选择（卧铺专用，上/中/下） -->
                <!-- 铺位类型（卧铺专用，上/中/下铺选择） -->
                <div class="form-group" v-if="sleeperTypes.includes(form.seatType)">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">铺位类型</label>
                  <select 
                    v-model="form.berthType" 
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all appearance-none"
                    required
                  >
                    <option value="">选择铺位</option>
                    <option value="上">上铺</option>
                    <option value="中">中铺</option>
                    <option value="下">下铺</option>
                  </select>
                </div>
                <div class="form-group">
                  <label v-if="sleeperTypes.includes(form.seatType)" class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">铺位号</label>
                  <label v-else class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">座位号</label>
                  <input 
                    v-model="form.seatNumber" 
                    type="text" 
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：12F"
                    pattern="[0-9]{1,2}[A-Fa-f]"
                    title="1-2位数字+A-F字母，例12F、5A"
                    required
                  >
                </div>
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">票价（元）</label>
                  <input
                    v-model="form.price"
                    type="number"
                    step="0.5"
                    min="0"
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：443.5"
                    required
                  >
                  <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">支持小数点后1位，例443或443.5</p>
                </div>
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">票号</label>
                  <input
                    v-model="form.serial"
                    type="text"
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：283K104567"
                    required
                  >
                </div>
                <!-- 座位/价格信息区域 - 新增优惠类型选择 -->
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">优惠类型</label>
                  <select
                    v-model="form.discountType"
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all appearance-none"
                  >
                    <option value="">无优惠</option>
                    <option value="student">学生票（学+惠）</option>
                    <option value="child">儿童票（儿）</option>
                    <option value="military">残疾军人票（军）</option>
                    <option value="disabled">残疾人票（残）</option>
                    <option value="elder">老人优惠票（老）</option>
                    <option value="discount">普通优惠票（惠）</option>
                    <option value="group">团体票（团）</option>
                    <option value="worker-group">务工团体票（工）</option>
                    <option value="student-group">学生团体票（学+团）</option>
                  </select>
                </div>
              </div>
            </div>

            <!-- 4. 乘客/售票信息 -->
            <div>
              <h3 class="text-lg font-semibold text-gray-700 dark:text-gray-200 mb-3 flex items-center">
                <span class="w-6 h-6 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded-full flex items-center justify-center mr-2 text-sm">
                  🧑
                </span>
                乘客/售票
              </h3>
              <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">乘客姓名</label>
                  <input
                    v-model="form.passengerName"
                    type="text"
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：张三"
                    required
                  >
                </div>
                <div class="form-group">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">身份证号</label>
                  <input
                    v-model="form.idNumber"
                    type="text"
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：3201021990****5678"
                    title="18位身份证号，最后一位可填X"
                    required
                  >
                </div>
                <div class="form-group col-span-1">
                  <label class="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">底部售票信息</label>
                  <input 
                    v-model="form.footerInfo" 
                    type="text" 
                    class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="例：65773311920607K104567　北京南售"
                    required
                  >
                  <p class="text-xs text-gray-500 dark:text-gray-400 mt-1"></p>
                </div>
              </div>
            </div>

            <!-- 保存图片按钮：移动端更大点击区域 -->
            <button
              type="submit"
              class="w-full bg-blue-600 hover:bg-blue-700 text-white py-4 px-6 rounded-lg font-medium transition-colors mt-4 flex items-center justify-center gap-2 text-lg shadow-lg shadow-blue-500/20"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
              </svg>
              保存火车票为图片
            </button>
          </form>
        </div>
        <!-- 预览区：桌面端在右侧 -->
        <div class="bg-white flex flex-col dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-6 transition-colors duration-300">
          <h3 class="text-lg font-semibold text-gray-700 dark:text-gray-200 mb-4 flex items-center">
            <span class="w-6 h-6 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-full flex items-center justify-center mr-2 text-sm">
              👀
            </span>
            实时预览
          </h3>
            <!-- 火车票组件：根据屏幕尺寸动态调整缩放比例 -->
             <div class="preview-container">
              <TrainTicket
                :serial="form.serial"
                :gate="form.gate"
                :fromStation="form.fromStation"
                :fromPinyin="form.fromPinyin"
                :toStation="form.toStation"
                :toPinyin="form.toPinyin"
                :trainCode="form.trainCode"
                :dateTime="form.dateTime"
                :carriage="form.carriage"
                :seatNumber="form.seatNumber"
                :berthType="form.berthType"
                :price="form.price"
                :seatType="form.seatType"
                :idNumber="form.idNumber"
                :passengerName="form.passengerName"
                :footerInfo="form.footerInfo"
                :discountType="form.discountType"
              />
            </div>
            <!-- 隐藏的原始尺寸车票，用于导出 -->
            <div 
                class="fixed top-0 left-0 w-[856px] h-[540px] bg-white z-[-1] opacity-0 pointer-events-none"
                id="hidden-ticket-area"
              >
              <TrainTicket
                ref="hiddenTicketRef"
                :serial="form.serial"
                :gate="form.gate"
                :fromStation="form.fromStation"
                :fromPinyin="form.fromPinyin"
                :toStation="form.toStation"
                :toPinyin="form.toPinyin"
                :trainCode="form.trainCode"
                :dateTime="form.dateTime"
                :carriage="form.carriage"
                :seatNumber="form.seatNumber"
                :berthType="form.berthType"
                :price="form.price"
                :seatType="form.seatType"
                :idNumber="form.idNumber"
                :passengerName="form.passengerName"
                :footerInfo="form.footerInfo"
                :discountType="form.discountType"
              />
            </div>
        </div>
      </div>
    </div>
  </div>
</template>


<script setup>
import { ref, reactive, onMounted, nextTick, watch, computed} from 'vue';
import TrainTicket from '@/components/TrainTicket.vue';
import { toPng } from "html-to-image";
import { ElMessage } from 'element-plus';


// 表单初始数据
const form = reactive({
  serial: '',
  gate: '',
  fromStation: '',
  fromPinyin: '',
  toStation: '',
  toPinyin: '',
  trainCode: '',
  dateTime: '',
  carriage: '',
  seatNumber: '',
  price: '',
  seatType: '',
  idNumber: '',
  passengerName: '',
  footerInfo: '',
  discountType: '',
  berthType: '',
  berthNumber: '',
});

// 定义卧铺类型列表（用于判断是否显示铺位选择）
const sleeperTypes = ref([
  '软卧', '硬卧', '动卧', '高级软卧', '一等卧', '二等卧'
]);

// 铺位类型选项
const berthOptions = ref([
  { label: '上铺', value: '上' },
  { label: '中铺', value: '中' },
  { label: '下铺', value: '下' }
]);

// 监听座位类型变化，重置铺位信息
watch(() => form.seatType, (newVal) => {
  if (!sleeperTypes.value.includes(newVal)) {
    form.berthType = '';
    form.berthNumber = '';
  }
});

// 计算最终座位号（铺位号+铺位类型）
const finalSeatNumber = computed(() => {
  if (sleeperTypes.value.includes(form.seatType) && form.berthNumber && form.berthType) {
    return `${form.berthNumber}${form.berthType}`;
  }
  return form.seatNumber;
});

// 火车票组件ref
const ticketRef = ref(null);
const hiddenTicketRef = ref(null);
// 修正保存图片的逻辑
const handleSaveImage = async () => {
  try {
    const node = hiddenTicketRef.value?.$el;
    const dataUrl = await toPng(node, {
      cacheBust: true,
      backgroundColor: "#fff",
      quality: 1,
      pixelRatio: 3,
    });


    // 4. 生成并下载图片
    // const imgUrl = canvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.href = dataUrl;
    link.download = `${form.trainCode}_${form.passengerName}_火车票.png`;
    link.click();
    link.remove();
  } catch (error) {
    ElMessage.error('图片保存失败，请重试！');
    console.error('保存图片错误：', error);
  }
};
</script>

<style lang="css">
.container {
  width: 100%;
  justify-content: center;
  align-items: center;
  /* overflow: hidden; */
}
@media screen and (max-width: 640px) {
  .preview-container {
    max-width: 80vw;
  }
}
</style>
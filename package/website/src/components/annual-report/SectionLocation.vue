<template>
  <ReportPage class="section-location" :class="{ 'animate-in': isActive }">
    <div class="h-full w-full flex flex-col p-0" ref="sectionRef">
      <!-- 标题区域 -->
      <div class="text-center mb-6 fade-in-up" :style="{ animationDelay: '0.1s' }">
        <h2 class="text-2xl font-bold text-orange-500 mb-2">步履所至 · 年度足迹地图</h2>
        <p class="text-sm text-slate-600 dark:text-slate-600 font-light">用镜头丈量山河，每一座城，都藏着你的独家时光</p>
      </div>

      <!-- 上半部分：地域数据汇总区 -->
      <div class="flex flex-col gap-4 mb-6">
        <div class="flex justify-between items-center gap-4">
          <!-- 省份卡片 -->
          <div class="flex-1 bg-[#FDFBF7] dark:bg-[#2A2A2A] rounded-2xl p-2 border border-slate-100 dark:border-slate-800 shadow-sm fade-in-left" :style="{ animationDelay: '0.2s' }">
             <div class="flex flex-col items-center justify-center h-full gap-1">
                <i class="mgc_earth_line text-2xl text-orange-500"></i>
                <div class="flex items-baseline gap-1">
                   <span class="text-3xl font-black text-orange-500 font-mono">{{ displayProvince }}</span>
                   <span class="text-xs text-slate-500">省</span>
                </div>
                <p class="text-xs text-slate-600 font-light text-center">山河万里，步履所至</p>
             </div>
          </div>

          <!-- 城市卡片 -->
          <div class="flex-1 bg-[#FDFBF7] dark:bg-[#2A2A2A] rounded-2xl p-2 border border-slate-100 dark:border-slate-800 shadow-sm fade-in-right" :style="{ animationDelay: '0.2s' }">
             <div class="flex flex-col items-center justify-center h-full gap-1">
                <i class="mgc_building_2_line text-2xl text-orange-500"></i>
                <div class="flex items-baseline gap-1">
                   <span class="text-3xl font-black text-orange-500 font-mono">{{ displayCity }}</span>
                   <span class="text-xs text-slate-500">城市</span>
                </div>
                <p class="text-xs text-slate-600 font-light text-center">一城一景，皆是回忆</p>
             </div>
          </div>
        </div>
        
        <!-- TOP1 城市补充 -->
        <div v-if="data.topCities && data.topCities.length > 0" class="text-center fade-in-up" :style="{ animationDelay: '0.5s' }">
           <p class="text-xs text-slate-600 font-light">
             ✨ 年度打卡最多：<span class="text-orange-500 font-bold">{{ data.topCities[0].cityName }}</span>（共{{ data.topCities[0].photoCount }}张照片）｜你的脚步，偏爱这座烟火小城
           </p>
        </div>
      </div>

      <!-- 下半部分：可视化地图核心区 -->
      <div class="flex-1 relative w-full h-full min-h-0 bg-white dark:bg-[#1E1E1E] rounded-xl border border-slate-100 dark:border-slate-800 overflow-hidden fade-in-up" :style="{ animationDelay: '0.6s' }">
         <div ref="mapContainer" class="w-full h-full absolute inset-0"></div>
         
         <!-- 地图加载中/失败 兜底 -->
         <div v-if="mapStatus !== 'loaded'" class="absolute inset-0 flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900 z-10">
            <template v-if="mapStatus === 'loading'">
               <div class="animate-pulse flex flex-col items-center">
                  <i class="mgc_map_2_line text-4xl text-slate-300 mb-2"></i>
                  <span class="text-xs text-slate-600">足迹加载中，稍等片刻...</span>
               </div>
            </template>
            <template v-else-if="mapStatus === 'error'">
               <div class="flex flex-col items-center" @click="initMap">
                  <i class="mgc_ghost_line text-4xl text-slate-300 mb-2"></i>
                  <span class="text-xs text-slate-600">地图走丢了，点击重试</span>
               </div>
            </template>
            <template v-else-if="mapStatus === 'empty'">
               <div class="flex flex-col items-center">
                  <i class="mgc_footprint_line text-4xl text-slate-300 mb-2"></i>
                  <span class="text-xs text-slate-600">暂未留下足迹印记</span>
                  <span class="text-[10px] text-slate-300 mt-1">下一年，愿你奔赴山海</span>
               </div>
            </template>
         </div>
      </div>
    </div>
  </ReportPage>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue';
import ReportPage from './ReportPage.vue';
import type { LocationMetrics } from '@/types/annualReport';
import { echarts } from '@/utils/echarts';
import { useIntersectionObserver } from '@vueuse/core';

const props = defineProps<{
  data: LocationMetrics;
}>();

const isActive = ref(false);
const sectionRef = ref<HTMLElement | null>(null);

useIntersectionObserver(
  sectionRef,
  ([{ isIntersecting }]) => {
    if (isIntersecting && !isActive.value) {
      isActive.value = true;
    }
  },
  { threshold: 0.5 }
);

const displayProvince = ref(0);
const displayCity = ref(0);
const mapContainer = ref<HTMLElement | null>(null);
const mapStatus = ref<'loading' | 'loaded' | 'error' | 'empty'>('loading');
let myMap: echarts.ECharts | null = null;

// 数字滚动动画
const animateValue = (start: number, end: number, duration: number, callback: (val: number) => void) => {
  const startTime = performance.now();
  const animate = (currentTime: number) => {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    
    // EaseOutExpo
    const easeProgress = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
    
    const value = Math.floor(start + (end - start) * easeProgress);
    callback(value);

    if (progress < 1) {
      requestAnimationFrame(animate);
    }
  };
  requestAnimationFrame(animate);
};

// 监听 isActive 触发动画
watch(isActive, (newVal) => {
  if (newVal) {
    // 重置并开始计数动画
    displayProvince.value = 0;
    displayCity.value = 0;
    setTimeout(() => {
       animateValue(0, props.data.lightenProvinceNum, 1200, (val) => displayProvince.value = val);
       animateValue(0, props.data.lightenCityNum, 1200, (val) => displayCity.value = val);
    }, 100);
    
    // 如果地图未加载，尝试加载
    if (!myMap) {
        initMap();
    } else {
        myMap.resize();
    }
  }
});

const initMap = async () => {
  if (!mapContainer.value) return;
  
  if (props.data.locationPoints.length === 0) {
      mapStatus.value = 'empty';
      return;
  }

  mapStatus.value = 'loading';
  
  try {
      // 获取地图数据
      const response = await fetch('/api/medias/geojson?level=city');
      if (!response.ok) throw new Error('Map fetch failed');
      const chinaJson = await response.json();

      echarts.registerMap('china', chinaJson);

      myMap = echarts.init(mapContainer.value);

      renderMap();
      mapStatus.value = 'loaded';

      // 监听窗口大小变化
      window.addEventListener('resize', handleResize);
  } catch (e) {
      console.error(e);
      mapStatus.value = 'error';
  }
};

const renderMap = () => {
    if (!myMap) return;

    // 收集所有有数据的城市名称
    const cityNames = new Set(props.data.locationPoints.map(p => p.name));
    const isMobile = window.innerWidth < 768
    // 构建 regions：只把有数据的城市区域点亮
    const mapData = props.data.locationPoints.map(p => ({
        name: p.name,
        itemStyle: {
            areaColor: p.name === props.data.topCities[0]?.cityName ? '#F97316' : '#FDBA74'
        },
        emphasis: {
            itemStyle: {
                areaColor: p.name === props.data.topCities[0]?.cityName ? '#EA580C' : '#FB923C'
            }
        }
    }));

    const scatterData = props.data.locationPoints.map(p => ({
        name: p.name,
        value: [p.lng, p.lat, p.count],
        coverUrl: p.coverUrl,
        itemStyle: {
            color: p.name === props.data.topCities[0]?.cityName ? '#F97316' : '#FDBA74'
        }
    }));

    const cityData = props.data.locationPoints.map(c => ({
        name: c.name,
        value: [c.lng, c.lat, c.count],
        coverUrl: c.coverUrl,
        itemStyle: {
            color: c.name === props.data.topCities[0]?.cityName ? '#F97316' : '#FDBA74'
        }
    }));
    const topCity = props.data.topCities[0];
    
    // 计算包围盒
    let minLng = 180, maxLng = -180, minLat = 90, maxLat = -90;
    props.data.locationPoints.forEach(p => {
        minLng = Math.min(minLng, p.lng);
        maxLng = Math.max(maxLng, p.lng);
        minLat = Math.min(minLat, p.lat);
        maxLat = Math.max(maxLat, p.lat);
    });

    // 添加内边距 (20%)
    const lngSpan = maxLng - minLng || 0.5;
    const latSpan = maxLat - minLat || 0.5;
    const paddingFactor = 0.2;
    
    const boundingCoords = [
        [minLng - lngSpan * paddingFactor, maxLat + latSpan * paddingFactor],
        [maxLng + lngSpan * paddingFactor, minLat - latSpan * paddingFactor]
    ];

    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#F97316',
            textStyle: { color: '#333' },
            padding: 0,
            formatter: (params: any) => {
                if (params.data && params.data.value) {
                    const data = params.data;
                    const imgHtml = data.coverUrl
                        ? `<div style="width: 140px; height: 90px; border-radius: 8px 8px 0 0; overflow: hidden; background-color: #f1f5f9;">
                             <img src="${data.coverUrl}" style="width: 100%; height: 100%; object-fit: cover;" />
                           </div>`
                        : '';
                    const paddingStyle = 'padding: 12px;';
                    return `
                        <div style="border-radius: 8px; overflow: hidden;">
                           ${imgHtml}
                           <div style="${paddingStyle}">
                               <div style="font-weight: bold; color: #F97316; margin-bottom: 2px;">${data.name}</div>
                               <div style="font-size: 12px; color: #64748b;">共拍摄 ${data.value[2]} 张照片</div>
                           </div>
                        </div>
                    `;
                }
                return params.name;
            }
        },
        geo: {
            map: 'china',
            roam: true, // 允许缩放
            boundingCoords: boundingCoords,
            label: { emphasis: { show: false } },
            itemStyle: {
                normal: {
                    areaColor: '#f1f5f9', // 默认浅灰
                    borderColor: '#cbd5e1',
                    borderWidth: 1
                },
                emphasis: {
                    areaColor: '#e2e8f0'
                }
            },
            regions: mapData
        },
        series: [
            {
                name: 'Top1焦点',
                type: 'effectScatter',
                coordinateSystem: 'geo',
                data: topCity ? scatterData.filter(p => p.name === topCity.cityName) : [],
                symbolSize: isMobile ? 8 : 12,
                showEffectOn: 'render',
                rippleEffect: {
                    brushType: 'stroke',
                    scale: 3
                },
                label: {
                    show: false,
                    formatter: '{b}',
                    position: 'right',
                    color: '#F97316',
                    fontWeight: 'bold',
                    fontSize: 12,
                    backgroundColor: 'rgba(255,255,255,0.9)',
                    padding: [4, 8],
                    borderRadius: 4,
                    shadowColor: 'rgba(0, 0, 0, 0.1)',
                    shadowBlur: 4
                },
                itemStyle: {
                    color: '#F97316',
                    shadowBlur: 10,
                    shadowColor: '#333'
                },
                zlevel: 1
            },
            {
              name: '照片数量',
              type: 'map',
              geoIndex: 0,
              data: cityData,
              // Add specific border to data items to make them pop against empty regions
              itemStyle: {
                borderColor:  '#fff',
                borderWidth: 0.5
              }
            }
        ]
    };

    myMap.setOption(option);
};

const handleResize = () => {
    myMap?.resize();
};

onUnmounted(() => {
    window.removeEventListener('resize', handleResize);
    myMap?.dispose();
});

</script>

<style scoped>
.animate-in .fade-in-up {
  animation: fadeInUp 0.8s ease-out forwards;
  opacity: 0;
}

.animate-in .fade-in-left {
  animation: fadeInLeft 0.8s ease-out forwards;
  opacity: 0;
}

.animate-in .fade-in-right {
  animation: fadeInRight 0.8s ease-out forwards;
  opacity: 0;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeInLeft {
  from {
    opacity: 0;
    transform: translateX(-20px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes fadeInRight {
  from {
    opacity: 0;
    transform: translateX(20px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
</style>

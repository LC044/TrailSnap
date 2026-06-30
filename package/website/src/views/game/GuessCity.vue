<template>
  <div class="h-full flex flex-col md:flex-row gap-4 p-4 lg:p-6 bg-slate-50 dark:bg-slate-900 overflow-hidden relative">
    
    <!-- Header/Title -->
    <div class="absolute top-4 left-6 z-10 hidden md:block pointer-events-none">
      <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100 flex items-center gap-2">
        <i class="mgc_location_line text-primary-500"></i>
        猜城市
      </h1>
      <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">根据照片和时间提示，猜猜这是哪座城市</p>
    </div>

    <!-- Game Layout -->
    <div class="flex-1 flex flex-col md:flex-row gap-4 max-w-6xl mx-auto w-full h-full pb-16 md:pb-0">
      
      <!-- Photo Area -->
      <div class="flex-1 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700 overflow-hidden relative group">
        <template v-if="photoId">
          <img 
            :src="`/api/medias/${photoId}/file`" 
            class="w-full h-full object-contain bg-gray-100 dark:bg-gray-900"
          />
        </template>
        <div v-else class="w-full h-full flex items-center justify-center bg-gray-100 dark:bg-gray-900">
          <Loader2 class="animate-spin text-4xl text-primary-500 w-10 h-10" />
        </div>
      </div>

      <!-- Interaction Area -->
      <div class="w-full md:w-80 flex flex-col gap-4">
        <div class="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700 p-4 md:p-6 flex flex-col gap-4 h-full md:h-auto overflow-y-auto">
          
          <div class="flex justify-between items-center md:hidden">
            <h1 class="text-xl font-bold text-gray-800 dark:text-gray-100">猜城市</h1>
          </div>

          <!-- Attempts Left -->
          <div class="flex items-center justify-between">
            <span class="text-sm font-medium text-gray-600 dark:text-gray-300">剩余次数</span>
            <div class="flex gap-1.5">
              <div 
                v-for="i in 5" 
                :key="i"
                class="w-3 h-3 rounded-full transition-colors duration-300"
                :class="i <= (5 - attempts) ? 'bg-primary-500' : 'bg-gray-200 dark:bg-gray-700'"
              ></div>
            </div>
          </div>

          <!-- Time Hint -->
          <div class="bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300 rounded-lg p-3 flex items-center gap-3">
            <CalendarCheck class="w-5 h-5 shrink-0" />
            <div class="flex-1 font-medium">
              时间提示：{{ timeHint }}
            </div>
          </div>

          <!-- Input Area -->
          <div class="mt-2">
            <el-autocomplete
              v-model="guessInput"
              :fetch-suggestions="querySearch"
              placeholder="输入城市名..."
              class="w-full"
              size="large"
              clearable
              @select="handleGuess"
              @keyup.enter="handleGuess"
              :disabled="gameState !== 'playing'"
            >
              <template #append>
                <el-button type="primary" @click="handleGuess" :disabled="gameState !== 'playing'">猜</el-button>
              </template>
            </el-autocomplete>
            <div v-if="errorMessage" class="text-red-500 text-xs mt-1">{{ errorMessage }}</div>
          </div>

          <!-- Feedback List -->
          <div class="flex-1 flex flex-col gap-2 mt-4 overflow-y-auto">
            <div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1" v-if="guesses.length">历史猜测</div>
            <div 
              v-for="(guess, index) in [...guesses].reverse()" 
              :key="index"
              class="text-sm p-2 rounded bg-gray-50 dark:bg-gray-700/50 text-gray-700 dark:text-gray-300 animate-fade-in"
            >
              <span class="text-red-500 font-bold mr-2">✗</span>
              你猜：{{ guess.city }}
              <br/>
              <span class="text-xs text-gray-500 dark:text-gray-400 ml-5">
                实际在 <span class="font-medium text-gray-700 dark:text-gray-300">{{ guess.direction }}</span> · 约 <span class="font-medium text-gray-700 dark:text-gray-300">{{ Math.round(guess.distance) }}km</span>
              </span>
            </div>
          </div>
          
        </div>
      </div>
    </div>

    <!-- Settlement Overlay (Fullscreen) -->
    <div v-if="gameState !== 'playing'" class="fixed inset-0 z-50 flex items-center justify-center bg-black/90 animate-fade-in">
      <img 
        v-if="photoId"
        :src="`/api/medias/${photoId}/thumbnail?size=medium`" 
        class="absolute inset-0 w-full h-full object-cover blur-2xl opacity-50 scale-110"
      />
      <div class="absolute inset-0 bg-white/30 dark:bg-black/40 backdrop-blur-sm"></div>

      <!-- Result Banner -->
      <div class="absolute top-10 md:top-16 left-0 right-0 text-center z-20">
        <h2 class="text-4xl md:text-5xl font-bold text-white drop-shadow-lg mb-2">
          {{ gameState === 'won' ? '🎉 挑战成功！' : '🥺 挑战失败' }}
        </h2>
        <p class="text-white/90 text-lg shadow-sm">
          {{ gameState === 'won' ? `你在第 ${attempts} 次猜中了答案` : '很遗憾，次数已用尽' }}
        </p>
      </div>

      <div class="relative z-10 transition-all duration-500 p-4 xl:p-8 bg-white dark:bg-gray-800 shadow-2xl rounded-lg md:rounded-xl border-[8px] xl:border-[16px] border-gray-100 dark:border-gray-700 max-w-[95vw] md:max-w-[90vw] max-h-[85vh] md:max-h-[90vh] flex flex-col w-fit h-fit overflow-hidden mt-16 md:mt-10">
        <img 
          :src="`/api/medias/${photoId}/file`" 
          class="w-auto h-auto max-w-full max-h-[50vh] md:max-h-[60vh] object-contain mx-auto rounded-sm shadow-sm"
        />

        <!-- Info Overlay -->
        <div class="mt-3 xl:mt-4 px-1 xl:px-2 flex flex-col gap-1 text-gray-700 dark:text-gray-300">
          <div class="flex flex-col md:flex-row xl:items-center justify-between gap-1">
              <div class="flex items-baseline gap-2 flex-wrap">
                    <span class="font-bold text-lg xl:text-xl whitespace-nowrap">{{ fullDate }}</span>
                    <span class="text-xs xl:text-sm opacity-80 whitespace-nowrap">({{ timeAgo }})</span>
              </div>
              <div class="text-xs font-medium flex items-center gap-1 opacity-70">
                    <MapPin class="w-4 h-4" />
                    <span class="truncate max-w-[200px] text-lg text-primary-500 font-bold">{{ actualCity }}</span>
              </div>
          </div>
          <div v-if="narrative" class="text-xs xl:text-sm font-serif italic opacity-90 leading-relaxed border-l-2 border-primary-500 pl-2 xl:pl-3 py-1 mt-1 xl:mt-0 line-clamp-3 xl:line-clamp-none">
              {{ narrative }}
          </div>
        </div>
      </div>

      <!-- Replay Button -->
      <div class="absolute bottom-10 md:bottom-16 left-0 right-0 flex justify-center z-20">
        <el-button type="primary" size="large" round class="px-8 shadow-xl" @click="startNewGame">
          再来一张
        </el-button>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { CalendarCheck, MapPin, Loader2 } from 'lucide-vue-next'
import { guessCityApi, type CityCoordinate } from '@/api/guessCity'
import { photoApi } from '@/api/photo'
import { format } from 'date-fns'

const photoId = ref<string>('')
const photoTime = ref<string | null>(null)
const actualCity = ref<string>('')
const narrative = ref<string>('')

const cities = ref<CityCoordinate[]>([])
const guessInput = ref('')
const errorMessage = ref('')
const attempts = ref(0)
const maxAttempts = 5
const gameState = ref<'playing' | 'won' | 'lost'>('playing')

interface GuessRecord {
  city: string
  distance: number
  direction: string
}
const guesses = ref<GuessRecord[]>([])

// Time Hint Logic
const timeHint = computed(() => {
  if (!photoTime.value) return '未知时间'
  try {
    const d = new Date(photoTime.value)
    if (attempts.value === 0) return format(d, 'yyyy年')
    if (attempts.value === 1) return format(d, 'yyyy年 MM月')
    return format(d, 'yyyy年 MM月 dd日')
  } catch (e) {
    return '未知时间'
  }
})

const fullDate = computed(() => {
  if (!photoTime.value) return ''
  try {
    return format(new Date(photoTime.value), 'yyyy-MM-dd')
  } catch (e) {
    return ''
  }
})

const timeAgo = computed(() => {
  if (!photoTime.value) return ''
  const date = new Date(photoTime.value)
  const currentYear = new Date().getFullYear()
  const photoYear = date.getFullYear()
  const years = currentYear - photoYear
  if (years <= 0) return '今年'
  return `${years} 年前`
})

// Auto Complete Search
const querySearch = (queryString: string, cb: any) => {
  const results = queryString
    ? cities.value.filter(createFilter(queryString))
    : cities.value
  cb(results.map(c => ({ value: c.city })))
}

const createFilter = (queryString: string) => {
  return (city: CityCoordinate) => {
    return city.city.toLowerCase().indexOf(queryString.toLowerCase()) !== -1
  }
}

const startNewGame = async () => {
  gameState.value = 'playing'
  attempts.value = 0
  guesses.value = []
  guessInput.value = ''
  errorMessage.value = ''
  photoId.value = ''
  photoTime.value = null
  actualCity.value = ''
  narrative.value = ''

  try {
    const res = await guessCityApi.getRandomPhoto()
    photoId.value = res.data.id
    photoTime.value = res.data.photo_time
  } catch (err: any) {
    errorMessage.value = err.message || '获取照片失败'
  }
}

const fetchCities = async () => {
  try {
    const res = await guessCityApi.getCities()
    cities.value = res.data
  } catch (err) {
    console.error('Failed to fetch cities', err)
  }
}

const handleGuess = async () => {
  if (gameState.value !== 'playing' || !guessInput.value.trim() || !photoId.value) return
  
  const city = guessInput.value.trim()
  
  // check if city exists in list
  const cityExists = cities.value.find(c => c.city === city)
  if (!cityExists) {
    errorMessage.value = '无法识别该城市，请重新输入或从列表中选择'
    return
  }
  
  errorMessage.value = ''
  
  try {
    const res = await guessCityApi.guessCity({ photo_id: photoId.value, guess_city: city })
    const data = res.data
    
    if (data.correct) {
      gameState.value = 'won'
      attempts.value++
      actualCity.value = data.actual_city
      await fetchPhotoDetails()
    } else {
      attempts.value++
      guesses.value.push({
        city: city,
        distance: data.distance_km,
        direction: data.direction
      })
      guessInput.value = ''
      
      if (attempts.value >= maxAttempts) {
        gameState.value = 'lost'
        actualCity.value = data.actual_city
        await fetchPhotoDetails()
      }
    }
  } catch (err: any) {
    errorMessage.value = err.message || '判断失败'
  }
}

const fetchPhotoDetails = async () => {
  try {
    const desc = await photoApi.getPhotoDescription(photoId.value)
    if (desc && desc.narrative) {
      narrative.value = desc.narrative
    }
  } catch (err) {
    console.error('Failed to fetch description', err)
  }
}

onMounted(() => {
  fetchCities()
  startNewGame()
})

</script>

<style scoped>
.animate-fade-in {
  animation: fadeIn 0.5s ease-out;
}
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>

<template>
  <ResponsiveDialog
    :model-value="visible"
    :title="creating ? '新建人物' : (title || '添加到人物相册')"
    max-width="26rem"
    :before-close="() => !submitting && !loading"
    @update:model-value="$emit('update:visible', $event)"
  >
    <div class="flex flex-col gap-4">
      <template v-if="creating">
        <label for="new-person-name" class="text-sm font-medium">人物姓名</label>
        <el-input id="new-person-name" v-model="newName" placeholder="输入姓名或称呼" maxlength="500" :disabled="loading || submitting" @keyup.enter="createPerson" />
        <p class="ts-muted text-sm leading-6">只有一张照片也可以新建人物。创建后会立即选中这个人物。</p>
      </template>
      <template v-else>
      <button type="button" class="ts-button ts-button-secondary w-full" :disabled="loading || submitting" @click="beginCreate"><Plus class="h-4 w-4" />新建人物</button>
      <el-input
        v-model="searchQuery"
        placeholder="搜索人物名称..."
        clearable
        :disabled="submitting || loading"
        :prefix-icon="Search"
        aria-label="搜索或输入新人物姓名"
      />

      <div class="h-[300px] overflow-y-auto border rounded-md p-2" v-loading="loading || submitting">
        <div v-if="loadError" class="ts-muted text-center py-4">人物加载失败<button class="ts-button ts-button-secondary ml-2" @click="loadPeople">重试</button></div>
        <div v-else-if="filteredPeople.length === 0 && !searchQuery && !loading" class="ts-muted text-center py-4">
          暂无人物数据
        </div>
        
        <button
          v-for="person in filteredPeople"
          :key="person.id"
          type="button"
          :disabled="loading || submitting"
          class="w-full text-left flex items-center p-2 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer rounded transition-colors disabled:opacity-50"
          @click="selectPerson(person)"
        >
          <PersonAvatar :person="person" />
          <div class="flex min-w-0 flex-1 flex-col">
            <span class="truncate font-medium">{{ person.identity_name }}</span>
            <span class="ts-muted text-xs">{{ person.face_count }} 张照片</span>
          </div>
        </button>

        <button
          v-if="showCreateOption"
          type="button"
          :disabled="loading || submitting || loadError"
          class="w-full text-left flex items-center p-2 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer rounded transition-colors text-primary-600 dark:text-primary-400 disabled:opacity-50"
          @click="beginCreate"
        >
          <div class="w-10 h-10 shrink-0 rounded-full flex items-center justify-center mr-3 bg-primary-100 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400">
            <el-icon><Plus /></el-icon>
          </div>
          <span class="font-medium break-all">创建并选择“{{ searchQuery.trim() }}”</span>
        </button>
      </div>
      </template>
    </div>
    <template v-if="creating" #footer>
      <div class="flex justify-end gap-2">
        <button type="button" class="ts-button ts-button-secondary" :disabled="loading || submitting" @click="creating = false">返回选择</button>
        <button type="button" class="ts-button ts-button-primary" :disabled="!newName.trim() || loading || submitting" @click="createPerson">{{ loading || submitting ? '正在创建…' : '创建并选择' }}</button>
      </div>
    </template>
  </ResponsiveDialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Search, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ResponsiveDialog from './ui/ResponsiveDialog.vue'
import PersonAvatar from '@/components/PersonAvatar.vue'
import { faceApi } from '@/api/face'
import type { FaceIdentity } from '@/types/album'

const props = defineProps<{
  visible: boolean
  submitting?: boolean
  title?: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'select', identity: FaceIdentity): void
}>()

const searchQuery = ref('')
const creating = ref(false)
const newName = ref('')
const people = ref<FaceIdentity[]>([])
const loading = ref(false)
const loadError = ref(false)
let requestVersion = 0

const filteredPeople = computed(() => {
  if (!searchQuery.value) return people.value
  const query = searchQuery.value.trim().toLowerCase()
  return people.value.filter(p => 
    p.identity_name && p.identity_name.toLowerCase().includes(query)
  )
})

const showCreateOption = computed(() => {
  return searchQuery.value.trim() && !filteredPeople.value.some(p => p.identity_name === searchQuery.value.trim())
})

const loadPeople = async () => {
  const request = ++requestVersion
  loading.value = true
  loadError.value = false
  people.value = []
  try {
    for (let page = 1; ; page++) {
      const batch = await faceApi.listIdentities(page, 200, ['named'], 0)
      if (request !== requestVersion || !props.visible) return
      people.value.push(...batch)
      if (batch.length < 200) break
    }
  } catch (e) {
    if (request === requestVersion) loadError.value = true
    console.error(e)
  } finally {
    if (request === requestVersion) loading.value = false
  }
}

watch(() => props.visible, (val) => {
  if (val) {
    searchQuery.value = ''
    creating.value = false
    newName.value = ''
    loadPeople()
  } else {
    ++requestVersion
    loading.value = false
  }
})

const selectPerson = (person: FaceIdentity) => {
  if (props.submitting || loading.value) return
  emit('select', person)
}

const beginCreate = () => {
  newName.value = searchQuery.value.trim()
  creating.value = true
}

const createPerson = async () => {
  if (!newName.value.trim() || props.submitting || loading.value) return
  const request = requestVersion
  try {
    loading.value = true
    const newPerson = await faceApi.createIdentity({
      identity_name: newName.value.trim()
    })
    if (request !== requestVersion || !props.visible) return
    emit('select', newPerson)
  } catch (e) {
    ElMessage.error('创建人物失败，请重试')
    console.error(e)
  } finally {
    if (request === requestVersion) loading.value = false
  }
}
</script>

<template>
  <div>
    <div v-if="loading" class="flex justify-center items-center py-20">
      <div class="w-10 h-10 border-4 border-slate-200 dark:border-slate-700 border-t-primary-500 rounded-full animate-spin"></div>
    </div>

    <div v-else-if="error" class="flex flex-col items-center justify-center py-20 text-center text-red-500">
      <X class="w-12 h-12 mb-4" />
      <h3 class="text-xl font-medium mb-2">数据加载失败</h3>
      <p class="mb-4">{{ error }}</p>
      <button @click="$emit('fetch-tickets')" class="px-4 py-2 bg-primary-500 text-white rounded-md hover:bg-primary-600 transition-colors">重试</button>
    </div>

    <div v-else-if="filteredTickets.length > 0" class="px-4">
      <TicketTimeline
        v-if="viewMode === 'timeline'"
        :tickets="filteredTickets"
        :selected-ticket-ids="selectedTickets"
        :current-theme="currentTheme"
        @toggle-select="$emit('toggle-select', $event)"
        @edit="$emit('edit', $event)"
        @delete="$emit('delete', $event)"
        @view-paper="$emit('view-paper', $event)"
        @view-photo="$emit('view-photo', $event)"
      />
      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <TicketCard
          v-for="ticket in filteredTickets"
          :key="ticket.id"
          :ticket="ticket"
          :selected-ticket-ids="selectedTickets"
          :current-theme="currentTheme"
          @toggle-select="$emit('toggle-select', $event)"
          @edit="$emit('edit', $event)"
          @delete="$emit('delete', $event)"
          @view-paper="$emit('view-paper', $event)"
          @view-photo="$emit('view-photo', $event)"
        />
      </div>
    </div>

    <div v-else class="flex flex-col items-center justify-center py-20 text-center">
      <div class="w-24 h-24 bg-slate-100 dark:bg-slate-800 rounded-full flex items-center justify-center mb-4">
        <TrainFront class="w-12 h-12 text-slate-300 dark:text-slate-600" />
      </div>
      <h3 class="text-xl font-medium text-slate-400 mb-2">暂无收藏车票</h3>
      <button @click="$emit('open-ticket-modal')" class="text-primary-500 hover:underline">点击新增添加你的第一张车票</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { X, TrainFront } from 'lucide-vue-next';
import TicketTimeline from '@/components/TicketTimeline.vue';
import TicketCard from '@/components/TicketCard.vue';
import type { TicketFrontend } from '@/types/ticket';
import type { ThemeColor } from '@/composables/useTheme';

defineProps<{
  loading: boolean;
  error: string | null;
  filteredTickets: TicketFrontend[];
  viewMode: string;
  selectedTickets: (number | string)[];
  currentTheme: ThemeColor;
}>();

defineEmits<{
  (e: 'fetch-tickets'): void;
  (e: 'toggle-select', id: number | string): void;
  (e: 'edit', ticket: TicketFrontend): void;
  (e: 'delete', id: number | string): void;
  (e: 'view-paper', ticket: TicketFrontend): void;
  (e: 'view-photo', ticket: TicketFrontend): void;
  (e: 'open-ticket-modal'): void;
}>();
</script>

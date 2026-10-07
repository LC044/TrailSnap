<template>
  <span
    class="relative block overflow-hidden bg-gray-100 dark:bg-gray-800"
    :class="
      large
        ? 'h-44 w-full rounded-2xl sm:h-52'
        : 'h-[72px] w-14 shrink-0 rounded-xl sm:h-20 sm:w-16'
    "
    aria-hidden="true"
  >
    <img
      v-if="photoId && !failed"
      :src="thumbnailUrl(photoId, large ? 'medium' : 'small')"
      alt=""
      loading="lazy"
      class="h-full w-full"
      :class="large ? 'object-contain' : 'object-cover'"
      @error="failed = true"
    />
    <span
      v-else
      class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-primary-500"
    >
      <component
        :is="type === 'train' ? TrainFront : type === 'flight' ? Plane : Ticket"
        :class="large ? 'h-10 w-10' : 'h-6 w-6'"
      />
      <span class="h-0.5 w-5 rounded-full bg-primary-200 dark:bg-primary-800" />
      <span class="h-0.5 w-3 rounded-full bg-primary-200 dark:bg-primary-800" />
    </span>
  </span>
</template>
<script setup lang="ts">
import { ref, watch } from "vue";
import { TrainFront, Plane, Ticket } from "lucide-vue-next";
import { thumbnailUrl } from "@/utils/mediaUrl";
const props = defineProps<{
  photoId?: string | null;
  type: string;
  large?: boolean;
}>();
const failed = ref(false);
watch(
  () => props.photoId,
  () => {
    failed.value = false;
  },
);
</script>

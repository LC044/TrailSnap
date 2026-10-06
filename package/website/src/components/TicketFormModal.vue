<template>
  <TicketEditorDialog
    type="train"
    :is-open="isOpen"
    :is-editing="isEditing"
    :initial-data="initialData"
    :saving="saving"
    @save="(data) => emit('save', data as TicketFormData)"
    @cancel="emit('cancel')"
  />
</template>
<script setup lang="ts">
import TicketEditorDialog from "@/views/ticket/components/TicketEditorDialog.vue";
import type { TicketFormData } from "@/types/ticket";
import type { ThemeColor } from "@/composables/useTheme";
defineProps<{
  isOpen: boolean;
  isEditing: boolean;
  initialData: Partial<TicketFormData>;
  currentTheme?: ThemeColor;
  saving: boolean;
  apiBaseUrl?: string;
}>();
const emit = defineEmits<{ save: [TicketFormData]; cancel: [] }>();
</script>

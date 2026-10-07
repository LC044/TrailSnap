<template>
  <ResponsiveDialog history
    :model-value="isOpen"
    :title="`${isEditing ? '编辑' : '新增'}${ticketLabel(type)}`"
    mobile-mode="fullscreen"
    mobile-back
    max-width="44rem"
    :close-on-backdrop="false"
    :before-close="confirmExit"
    @update:model-value="emit('cancel')"
  >
    <div class="ts-surface p-4 mb-5">
      <button
        class="ts-button ts-button-secondary"
        :disabled="recognizing || saving"
        @click="fileInput?.click()"
      >
        <Sparkles class="h-4 w-4" />{{
          recognizing ? "正在识别…" : "上传票据图片，智能填充"
        }}
      </button>
      <p class="text-xs mt-2 text-gray-500 dark:text-gray-400">
        识别后请检查字段，也可以直接手动填写。
      </p>
      <input
        ref="fileInput"
        class="hidden"
        type="file"
        accept="image/*"
        @change="recognize"
      />
    </div>
    <form
      ref="formElement"
      :id="formId"
      class="grid grid-cols-1 gap-4 md:grid-cols-2"
      @submit.prevent="submit"
    >
      <label class="text-sm md:col-span-2"
        >{{ type === "train" ? "车次" : "航班号"
        }}<input
          v-model="form.code"
          required
          maxlength="20"
          class="ts-input w-full mt-2"
          :aria-label="type === 'train' ? '车次' : '航班号'"
          placeholder="例如 G1920 / MU1234"
      /></label>
      <label class="text-sm"
        >{{ type === "train" ? "出发站" : "出发地"
        }}<input
          v-model="form.from"
          required
          maxlength="50"
          class="ts-input w-full mt-2"
          aria-label="出发地"
          :list="type === 'train' ? stationListId : undefined"
      /></label>
      <label class="text-sm"
        >{{ type === "train" ? "到达站" : "目的地"
        }}<input
          v-model="form.to"
          required
          maxlength="50"
          class="ts-input w-full mt-2"
          aria-label="目的地"
          :list="type === 'train' ? stationListId : undefined"
      /></label>
      <div v-if="type === 'train'" class="md:col-span-2">
        <button
          type="button"
          class="ts-button ts-button-ghost text-primary-600 dark:text-primary-400"
          :disabled="!form.code || schedulesLoading"
          @click="loadSchedules"
        >
          {{ schedulesLoading ? "查询中…" : "查询车次时刻表" }}
        </button>
        <p
          v-if="scheduleMessage"
          class="mt-1 text-xs text-gray-500 dark:text-gray-400"
        >
          {{ scheduleMessage }}
        </p>
        <datalist :id="stationListId">
          <option
            v-for="station in stations"
            :key="station.station_name"
            :value="station.station_name"
          />
        </datalist>
      </div>
      <label class="text-sm"
        >出发时间<input
          v-model="form.dateTime"
          required
          type="datetime-local"
          class="ts-input w-full mt-2 min-w-0"
          aria-label="出发时间"
      /></label>
      <label class="text-sm"
        >{{ type === "train" ? "乘车人" : "乘机人"
        }}<input
          v-model="form.name"
          required
          maxlength="50"
          class="ts-input w-full mt-2"
          :aria-label="type === 'train' ? '乘车人' : '乘机人'"
      /></label>
      <label class="text-sm"
        >票价（元）<input
          v-model.number="form.price"
          required
          type="number"
          min="0"
          step="0.01"
          class="ts-input w-full mt-2"
          aria-label="票价"
      /></label>
      <template v-if="type === 'train'">
        <label class="text-sm"
          >席别<select
            v-model="form.seatType"
            class="ts-input w-full mt-2"
            aria-label="席别"
          >
            <option
              v-for="seat in [
                '二等座',
                '一等座',
                '商务座',
                '硬座',
                '软座',
                '硬卧',
                '软卧',
                '无座',
              ]"
              :key="seat"
            >
              {{ seat }}
            </option>
          </select></label
        >
        <label class="text-sm"
          >车厢<input
            v-model="form.carriage"
            maxlength="10"
            class="ts-input w-full mt-2"
            aria-label="车厢" /></label
        ><label class="text-sm"
          >座位<input
            v-model="form.seatNumber"
            maxlength="10"
            :disabled="form.seatType === '无座'"
            class="ts-input w-full mt-2"
            aria-label="座位"
        /></label>
        <label class="text-sm"
          >铺位<select v-model="form.berthType" class="ts-input w-full mt-2">
            <option v-for="berth in ['无', '上', '中', '下']" :key="berth">
              {{ berth }}
            </option>
          </select></label
        >
        <label class="text-sm"
          >票种<select v-model="form.discountType" class="ts-input w-full mt-2">
            <option
              v-for="discount in ['全价票', '学生票', '儿童票', '优惠票']"
              :key="discount"
            >
              {{ discount }}
            </option>
          </select></label
        >
      </template>
      <details class="md:col-span-2 ts-surface p-3">
        <summary class="min-h-11 flex items-center cursor-pointer text-sm">
          补充交通数据
        </summary>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
          <label class="text-sm"
            >里程（km）<input
              v-model.number="form.distance"
              type="number"
              min="0"
              step="1"
              class="ts-input w-full mt-2" /></label
          ><label class="text-sm"
            >时长（分钟）<input
              v-model.number="form.totalRunningTime"
              type="number"
              min="0"
              step="1"
              class="ts-input w-full mt-2"
          /></label>
        </div>
      </details>
      <label class="md:col-span-2 text-sm"
        >备注<textarea
          v-model="form.comments"
          rows="3"
          maxlength="10000"
          class="ts-input w-full mt-2"
          placeholder="写下这段经历…"
        />
      </label>
    </form>
    <template #footer
      ><div class="flex gap-3">
        <button
          class="ts-button ts-button-secondary"
          :disabled="saving || recognizing"
          @click="cancel"
        >
          取消</button
        ><button
          class="ts-button ts-button-primary flex-1"
          type="submit"
          :form="formId"
          :disabled="saving || recognizing"
        >
          {{ saving ? "保存中…" : "保存票据" }}
        </button>
      </div></template
    >
  </ResponsiveDialog>
</template>
<script setup lang="ts">
import { ref, watch } from "vue";
import { onBeforeRouteLeave, onBeforeRouteUpdate, type RouteLocationNormalized } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Sparkles } from "lucide-vue-next";
import ResponsiveDialog from "@/components/ui/ResponsiveDialog.vue";
import { ticketService } from "@/api/ticketService";
import { ticketLabel, type SupportedTicketType } from "@/types/ticketWallet";
import type { TicketFormData, FlightTicketFormData } from "@/types/ticket";
const props = defineProps<{
  type: SupportedTicketType;
  isOpen: boolean;
  isEditing: boolean;
  saving: boolean;
  initialData: Partial<TicketFormData & FlightTicketFormData>;
}>();
const emit = defineEmits<{
  save: [TicketFormData | FlightTicketFormData];
  cancel: [];
}>();
const localNow = () => {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
};
const blank = () => ({
  code: "",
  from: "",
  to: "",
  dateTime: localNow(),
  name: "",
  price: 0,
  seatType: "二等座",
  carriage: "",
  seatNumber: "",
  berthType: "无",
  discountType: "全价票",
  distance: 0,
  totalRunningTime: 0,
  comments: "",
});
const form = ref(blank()),
  baseline = ref(""),
  formElement = ref<HTMLFormElement | null>(null),
  fileInput = ref<HTMLInputElement | null>(null),
  recognizing = ref(false),
  schedulesLoading = ref(false),
  scheduleMessage = ref("");
const formId = `ticket-editor-${props.type}`,
  stationListId = `ticket-stations-${props.type}`;
const stations = ref<
  Array<{
    station_name: string;
    accumulated_mileage: number;
    running_time: number;
    sequence: number;
  }>
>([]);
let generation = 0;
watch(
  () => props.isOpen,
  (value) => {
    generation++;
    if (!value) return;
    const data = props.initialData;
    form.value = {
      ...blank(),
      code: data.train_code || data.flight_code || "",
      from: data.from || data.departure_city || "",
      to: data.to || data.arrival_city || "",
      dateTime: (data.dateTime || data.date_time || localNow())
        .replace(" ", "T")
        .slice(0, 16),
      name: data.name || "",
      price: data.price ?? 0,
      seatType: data.seatType || "二等座",
      carriage: data.carriage || "",
      seatNumber: data.seatNumber || "",
      berthType: data.berthType || "无",
      discountType: data.discountType || "全价票",
      distance: data.distance ?? data.total_mileage ?? 0,
      totalRunningTime: data.totalRunningTime ?? data.total_running_time ?? 0,
      comments: data.comments || "",
    };
    baseline.value = JSON.stringify(form.value);
    stations.value = [];
    scheduleMessage.value = "";
    recognizing.value = false;
  },
  { immediate: true },
);
watch(
  () => form.value.seatType,
  (value) => {
    if (value === "无座") {
      form.value.seatNumber = "";
      form.value.berthType = "无";
    }
  },
);
watch(
  () => [form.value.from, form.value.to],
  () => {
    const from = stations.value.find(
        (station) => station.station_name === form.value.from,
      ),
      to = stations.value.find(
        (station) => station.station_name === form.value.to,
      );
    if (from && to && from.sequence < to.sequence) {
      form.value.distance = Math.max(
        0,
        to.accumulated_mileage - from.accumulated_mileage,
      );
      form.value.totalRunningTime = Math.max(
        0,
        to.running_time - from.running_time,
      );
    }
  },
);
async function confirmExit() {
  if (props.saving || recognizing.value) return false;
  if (JSON.stringify(form.value) !== baseline.value) {
    try {
      await ElMessageBox.confirm("放弃尚未保存的票据信息？", "放弃更改", {
        confirmButtonText: "放弃",
        cancelButtonText: "继续编辑",
      });
    } catch {
      return false;
    }
  }
  return true;
}
async function cancel() {
  if (await confirmExit()) emit("cancel");
}
const guardNavigation = async (to: RouteLocationNormalized, from: RouteLocationNormalized) => {
  if (to.fullPath === from.fullPath) return true;
  if (!props.isOpen) return true;
  const allowed = await confirmExit();
  if (allowed) baseline.value = JSON.stringify(form.value);
  return allowed;
};
onBeforeRouteLeave(guardNavigation);
onBeforeRouteUpdate(guardNavigation);
function submit() {
  if (props.saving || recognizing.value || !formElement.value?.reportValidity())
    return;
  const data = form.value;
  if (
    ![data.code, data.from, data.to, data.name].every((value) => value.trim())
  ) {
    ElMessage.warning("请完整填写车次/航班、起终点和乘车/乘机人");
    return;
  }
  if (
    ![data.price, data.distance, data.totalRunningTime].every(
      (value) => Number.isFinite(Number(value)) && Number(value) >= 0,
    )
  ) {
    ElMessage.warning("票价、里程和时长须为有效非负数");
    return;
  }
  if (props.type === "train")
    emit("save", {
      ...data,
      id: props.initialData.id,
      train_code: data.code.trim(),
      from: data.from.trim(),
      to: data.to.trim(),
      name: data.name.trim(),
      dateTime: data.dateTime.replace("T", " "),
    });
  else
    emit("save", {
      id: props.initialData.id,
      flight_code: data.code.trim(),
      departure_city: data.from.trim(),
      arrival_city: data.to.trim(),
      name: data.name.trim(),
      date_time: data.dateTime.replace("T", " "),
      price: data.price,
      total_mileage: data.distance,
      total_running_time: data.totalRunningTime,
      comments: data.comments,
    });
}
async function recognize(event: Event) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0];
  input.value = "";
  if (!file) return;
  const request = generation;
  recognizing.value = true;
  try {
    const data = await ticketService.recognizeByType(props.type, file);
    if (request !== generation) return;
    const map: Record<string, keyof ReturnType<typeof blank>> = {
      train_code: "code",
      flight_code: "code",
      departure_station: "from",
      arrival_station: "to",
      departure_city: "from",
      arrival_city: "to",
      name: "name",
      carriage: "carriage",
      seat_num: "seatNumber",
      berth_type: "berthType",
      seat_type: "seatType",
      discount_type: "discountType",
    };
    for (const [key, field] of Object.entries(map))
      if (data[key] !== undefined && data[key] !== null)
        (form.value as Record<string, unknown>)[field] = String(data[key]);
    if (data.datetime)
      form.value.dateTime = String(data.datetime)
        .replace(" ", "T")
        .slice(0, 16);
    if (data.price !== undefined) form.value.price = Number(data.price);
    ElMessage.success("已填充识别结果，请检查后保存");
  } catch {
    ElMessage.error("识别失败，可以继续手动填写");
  } finally {
    if (request === generation) recognizing.value = false;
  }
}
async function loadSchedules() {
  const code = form.value.code,
    request = generation;
  schedulesLoading.value = true;
  try {
    const result = await ticketService.trainSchedules(code);
    if (request !== generation || code !== form.value.code) return;
    stations.value = result.list || [];
    scheduleMessage.value = stations.value.length
      ? "选择站点后自动计算里程和时长"
      : "没有找到时刻表，可手动填写";
  } catch {
    scheduleMessage.value = "查询失败，可手动填写";
  } finally {
    schedulesLoading.value = false;
  }
}
</script>

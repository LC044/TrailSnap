<!-- src/components/RouteOutlet.vue -->
<template>
  <router-view v-slot="{ Component, route }">
    <!--
      One transition wrapping the cached and uncached views. KeepAlive's
      `include` list keeps the three heavy browse pages warm exactly as before
      (a component outside the list renders without being cached), while the
      page-turn transition gives every navigation a shared handover rhythm.
    -->
    <Transition :name="transitionName" mode="out-in">
      <KeepAlive :include="cachedPages">
        <component :is="Component" :key="route.path" />
      </KeepAlive>
    </Transition>
  </router-view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { pageDirection } from '@/composables/usePageDirection'

/** Pages whose state survives navigation; mirrors `meta.keepAlive` in the router. */
const cachedPages = ['HomePage', 'PhotosPage', 'TicketPage']

/* Stepping back lifts the previous page down from above instead of pushing a
   new one up, so the reader keeps their sense of place. */
const transitionName = computed(() => pageDirection.value === 'back' ? 'ts-page-back' : 'ts-page')
</script>

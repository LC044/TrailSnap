<script setup lang="ts">
import { computed } from 'vue'
import { useData } from 'vitepress'
import LandingHome from './LandingHome.vue'
import LegacyHome from './LegacyHome.vue'
const { lang } = useData()
const english = computed(() => lang.value.startsWith('en'))
</script>
<template><LegacyHome v-if="english" /><LandingHome v-else /></template>

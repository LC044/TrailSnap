<template>
  <main class="auth-page not-found">
    <section class="auth-panel missing-page">
      <div class="missing-image"><img :src="journalCover" alt="" /></div>
      <div class="auth-content">
        <h1 class="journal-page-title">页面未找到</h1>
        <p class="mt-2 text-sm ts-muted">链接可能已失效，或页面已经移动。</p>
        <RouterLink to="/" class="missing-home">返回首页 <ArrowUpRight aria-hidden="true" /></RouterLink>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ArrowUpRight } from 'lucide-vue-next'
import journalCover from '@/assets/journal-cover.webp'
import './login/auth.css'
</script>

<style scoped>
.missing-page { overflow: hidden; }
.missing-image { aspect-ratio: 2; overflow: hidden; }
.missing-image img { width: 100%; height: 100%; object-fit: cover; }
.missing-home { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; margin-top: 15px; padding-inline: 16px; border-radius: 999px; color: white; background: var(--ts-journal-action); font-size: 14px; font-weight: 650; }
.missing-home svg { width: 16px; height: 16px; }
</style>

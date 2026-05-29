<template>
  <div class="min-h-screen bg-white dark:bg-[#141414] text-neutral-dark dark:text-gray-100 font-sans overflow-x-hidden">
    <!-- 1. Navbar -->
    <div class="fixed top-0 md:top-6 md:left-1/2 md:-translate-x-1/2 z-50 transition-all duration-300 w-full md:w-max md:max-w-[95vw] px-0 md:px-2" :class="[isScrolled ? 'bg-white/80 dark:bg-[#141414]/80 backdrop-blur-xl border border-gray-200/50 dark:border-white/10 md:rounded-full md:shadow-[0_8px_32px_rgba(0,0,0,0.04),0_2px_8px_rgba(0,0,0,0.02)] md:dark:shadow-[0_8px_32px_rgba(0,0,0,0.2),0_2px_8px_rgba(0,0,0,0.1)]' : 'bg-neutral-light dark:bg-[#141414] border-none']">
      <nav class="px-4 md:px-6 py-1.5">
        <div class="flex justify-between items-center md:gap-8">
          <!-- Logo -->
          <div class="flex items-center cursor-pointer flex-shrink-0" @click="goLink(lang === 'zh-CN' ? '/' : '/en/')">
            <img src="/logo.svg" alt="行影集 Logo" class="w-8 h-8 mr-2">
            <div class="flex flex-col">
              <span class="text-lg font-bold text-neutral-dark dark:text-white leading-none">TrailSnap</span>
            </div>
          </div>

          <!-- Desktop Menu -->
          <div class="hidden md:flex items-center justify-center space-x-6 flex-1">
            <button type="button" class="transition-colors text-sm font-medium" :class="navClass('home')" @click="scrollTo('home')">{{ t.nav.home }}</button>
            <button type="button" class="transition-colors text-sm font-medium" :class="navClass('core-features')" @click="scrollTo('core-features')">{{ t.nav.features }}</button>
            <button type="button" class="transition-colors text-sm font-medium text-neutral-dark dark:text-gray-300 hover:text-primary" @click="goLink(lang === 'zh-CN' ? '/docs/guide/install' : '/en/docs/guide/install')">{{ t.nav.quickStart }}</button>
          </div>

          <!-- Desktop Buttons -->
          <div class="hidden md:flex items-center flex-shrink-0">
            <button class="px-5 py-2 rounded-full bg-neutral-dark dark:bg-white text-white dark:text-neutral-dark text-sm font-bold hover:scale-105 transition-transform shadow-sm" @click="goLink(lang === 'zh-CN' ? '/docs/guide/install' : '/en/docs/guide/install')">{{ t.nav.download }}</button>
          </div>

          <!-- Mobile Hamburger -->
          <div class="md:hidden flex items-center">
            <button @click="toggleMobileMenu" class="text-neutral-dark dark:text-white focus:outline-none">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
            </button>
          </div>
        </div>
      </nav>

      <!-- Mobile Menu -->
      <div v-if="isMobileMenuOpen" class="md:hidden absolute top-full left-0 right-0 mt-2 bg-white/95 dark:bg-[#141414]/95 backdrop-blur-xl rounded-2xl shadow-xl border border-gray-100 dark:border-gray-700 py-4 px-4 flex flex-col space-y-4">
        <button type="button" class="text-left w-fit transition-colors" :class="navClass('home')" @click="scrollTo('home')">{{ t.nav.home }}</button>
        <button type="button" class="text-left w-fit transition-colors" :class="navClass('core-features')" @click="scrollTo('core-features')">{{ t.nav.features }}</button>
        <button type="button" class="text-left w-fit transition-colors text-neutral-dark dark:text-gray-300 hover:text-primary" @click="goLink(lang === 'zh-CN' ? '/docs/guide/install' : '/en/docs/guide/install')">{{ t.nav.quickStart }}</button>
        <div class="flex space-x-4 pt-4 border-t border-gray-100 dark:border-gray-700">
          <button class="flex-1 py-2.5 rounded-xl bg-neutral-dark dark:bg-white text-white dark:text-neutral-dark font-bold shadow-sm" @click="goLink(lang === 'zh-CN' ? '/docs/guide/install' : '/en/docs/guide/install')">{{ t.nav.download }}</button>
        </div>
      </div>
    </div>

    <!-- 2. Hero Section -->
    <section id="home" class="relative pt-32 pb-20 lg:pt-40 lg:pb-32 bg-neutral-light dark:bg-[#141414]/50 overflow-hidden">
      <!-- Background Gradients -->
      <div class="absolute top-0 left-0 w-1/3 h-full bg-gradient-to-r from-blue-50 dark:from-blue-900/20 to-transparent opacity-50"></div>
      <div class="absolute bottom-0 right-0 w-1/3 h-full bg-gradient-to-l from-blue-50 dark:from-blue-900/20 to-transparent opacity-50"></div>

      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <div class="flex flex-col lg:flex-row items-center justify-between gap-12">
          <!-- Text Content -->
          <div class="w-full lg:w-[45%] text-center lg:text-left mb-8 lg:mb-0">
            <h1 class="text-3xl md:text-4xl lg:text-[42px] font-bold text-neutral-dark dark:text-white leading-tight mb-6">
              {{ t.hero.title1 }}<br>
              <span class="block mt-2">{{ t.hero.title2 }}</span>
            </h1>
            <p class="text-base md:text-lg text-neutral-gray dark:text-gray-400 mb-8 leading-relaxed max-w-2xl mx-auto lg:mx-0" v-html="t.hero.desc">
            </p>

            <!-- Tags -->
            <div class="flex flex-wrap justify-center lg:justify-start gap-3 mb-10">
              <span v-for="(tag, index) in t.hero.tags" :key="tag"
                    class="px-4 py-1.5 rounded-full text-sm font-medium hover:-translate-y-1 transition-transform cursor-default"
                    :class="[
                      index === 0 ? 'bg-slate-100 text-slate-700 dark:bg-[#141414]/40 dark:text-slate-300' :
                      index === 1 ? 'bg-teal-50 text-teal-700 dark:bg-teal-900/20 dark:text-teal-300' :
                      'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/20 dark:text-indigo-300'
                    ]">{{ tag }}</span>
            </div>

            <!-- Actions -->
            <div class="flex flex-col sm:flex-row justify-center lg:justify-start gap-4">
              <button class="px-8 py-3 rounded-lg bg-primary text-white font-bold hover:bg-primary-dark hover:scale-105 transition-all shadow-lg hover:shadow-xl" @click="goLink(lang === 'zh-CN' ? '/docs/guide/install' : '/en/docs/guide/install')">{{ t.hero.download }}</button>
              <button class="px-8 py-3 text-neutral-dark dark:text-gray-200 hover:text-primary dark:hover:text-primary transition-colors font-medium flex items-center justify-center gap-1" @click="goLink(lang === 'zh-CN' ? '/docs/guide/overview' : '/en/docs/guide/overview')">{{ t.hero.details }} <span class="text-xl">→</span></button>
            </div>
          </div>

          <!-- Visual Content (Chat Demo) -->
          <div class="w-full lg:w-[65%] relative flex justify-center">
            <div class="relative w-full max-w-[1280px] animate-float-slow">
              <!-- Mock Chat Window -->
              <div class="bg-gray-50 dark:bg-[#141414]/80 rounded-2xl shadow-xl overflow-hidden border border-gray-200 dark:border-slate-700 backdrop-blur-sm">
                <!-- Chat Header -->
                <div class="bg-white/80 dark:bg-[#141414]/80 border-b border-gray-100 dark:border-slate-700 px-4 py-3 flex items-center gap-3">
                  <div class="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary text-lg">🤖</div>
                  <div>
                    <div class="text-sm font-bold text-neutral-dark dark:text-white">TrailSnap AI</div>
                    <div class="text-xs text-green-500 flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-green-500 block"></span>{{ t.hero.chat.online }}</div>
                  </div>
                </div>
                
                <!-- Chat Body -->
                <div class="p-4 md:p-6 space-y-6 max-h-[680px] overflow-y-auto font-sans text-sm md:text-base custom-scrollbar">
                  <!-- User Message -->
                  <div class="flex justify-end animate-fade-in-up">
                    <div class="bg-[#8b5cf6] text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-[85%] shadow-sm leading-relaxed">
                      {{ t.hero.chat.userMsg }}
                    </div>
                  </div>
                  
                  <!-- AI Message -->
                  <div class="flex justify-start animate-fade-in-up" style="animation-delay: 0.5s; animation-fill-mode: both;">
                    <div class="bg-white dark:bg-[#1a1a1a] text-neutral-dark dark:text-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[90%] shadow-sm border border-gray-100 dark:border-slate-600 leading-relaxed">
                      <div class="typing-container">
                        <p class="mb-3">{{ t.hero.chat.aiMsg1 }}</p>
                        
                        <div class="mb-3">
                          <p class="font-bold text-neutral-dark dark:text-white mb-1.5 flex items-center gap-1.5"><span class="text-lg">📍</span> {{ t.hero.chat.itineraryTitle }}</p>
                          <ul class="space-y-1.5 text-[13px] md:text-sm text-neutral-gray dark:text-gray-300 ml-1">
                            <li v-for="(item, i) in t.hero.chat.itinerary" :key="i" class="flex gap-2">
                              <span class="min-w-[50px] md:min-w-[65px] font-medium text-[#8b5cf6] dark:text-[#a78bfa]">{{ item.date }}</span>
                              <span class="font-medium text-neutral-dark dark:text-gray-200">{{ item.desc }}</span>
                            </li>
                          </ul>
                        </div>
                        
                        <div class="mb-3">
                          <p class="font-bold text-neutral-dark dark:text-white mb-2 flex items-center gap-1.5"><span class="text-lg">📸</span> {{ t.hero.chat.photoTitle }}</p>
                          <div class="grid grid-cols-3 gap-2 thumbnails-container">
                            <img src="https://blog.siyuan.ink/static/img/83c62b2e4e7a6a24228dae753af1d815.thumbnail.webp" class="rounded-lg w-full h-20 md:h-24 object-cover hover:scale-105 transition-transform cursor-pointer shadow-sm" alt="photo1">
                            <img src="https://blog.siyuan.ink/static/img/cd23aeae6b77647a468a3cb027e5e417.thumbnail1.webp" class="rounded-lg w-full h-20 md:h-24 object-cover hover:scale-105 transition-transform cursor-pointer shadow-sm" alt="photo2">
                            <img src="https://blog.siyuan.ink/static/img/749352a60df84a4a4e218865d577b518.clipboard-2026-03-29.webp" class="rounded-lg w-full h-20 md:h-24 object-cover hover:scale-105 transition-transform cursor-pointer shadow-sm" alt="photo3">
                          </div>
                        </div>

                        <div class="mb-3">
                          <p class="font-bold text-neutral-dark dark:text-white mb-1.5 flex items-center gap-1.5"><span class="text-lg">💡</span> {{ t.hero.chat.copyTitle }}</p>
                          <p class="text-[13px] md:text-sm text-neutral-gray dark:text-gray-300 mb-1.5"><strong class="text-neutral-dark dark:text-gray-200">标题：</strong>{{ t.hero.chat.copyTitleText }}</p>
                          <p class="text-[13px] md:text-sm text-neutral-gray dark:text-gray-300 mb-1"><strong class="text-neutral-dark dark:text-gray-200">正文思路：</strong></p>
                          <ul class="space-y-1 text-[13px] md:text-sm text-neutral-gray dark:text-gray-300 ml-4 list-disc marker:text-primary">
                            <li v-for="(item, i) in t.hero.chat.copyBody" :key="i">{{ item }}</li>
                          </ul>
                        </div>

                        <div class="border-t border-gray-100 dark:border-gray-600 pt-3 mt-3">
                          <p class="text-[13px] md:text-sm text-neutral-gray dark:text-gray-300 mb-2 leading-relaxed" v-html="t.hero.chat.questionIntro"></p>
                          <ul class="space-y-1.5 text-[13px] md:text-sm text-neutral-gray dark:text-gray-300 mb-2">
                            <li v-for="(item, i) in t.hero.chat.questionOptions" :key="i" class="flex gap-1.5">
                              <span>{{ item.icon }}</span>
                              <span><strong class="text-neutral-dark dark:text-gray-200">{{ item.name }}：</strong>{{ item.desc }}</span>
                            </li>
                          </ul>
                          <p class="text-[13px] md:text-sm text-neutral-gray dark:text-gray-300">{{ t.hero.chat.questionOutro }}</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <!-- Decorative Elements -->
              <div class="absolute -top-6 -right-6 text-4xl opacity-20 text-primary animate-pulse z-0">✨</div>
              <div class="absolute -bottom-6 -left-6 w-24 h-24 bg-purple-400/20 dark:bg-[#a78bfa]/20 rounded-full blur-2xl z-0"></div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 2.5 Feature Screenshots -->
    <section class="py-20 bg-white dark:bg-[#141414]">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-16">
          <h2 class="text-3xl font-bold text-neutral-dark dark:text-white mb-4">{{ t.screenshots.title }}</h2>
          <div class="w-16 h-1 bg-primary mx-auto rounded-full"></div>
        </div>

        <div class="relative max-w-5xl mx-auto">
          <!-- Main Image Display -->
          <div class="relative aspect-video rounded-xl overflow-hidden shadow-2xl group bg-gray-100 dark:bg-[#141414]">
             <div v-for="(shot, index) in featureScreenshots" :key="index" 
                 class="absolute inset-0 transition-opacity duration-500 ease-in-out"
                 :class="index === activeScreenshotIndex ? 'opacity-100 z-10' : 'opacity-0 z-0'">
              <img v-if="shot.image" :src="shot.image" :alt="shot.title" class="w-full h-full object-cover" loading="lazy">
              <div v-else class="w-full h-full flex items-center justify-center text-gray-400 text-xl bg-gray-900">Image Placeholder: {{ shot.title }}</div>
              
              <!-- Caption Overlay -->
              <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2 md:p-8 text-white">
                <h3 class="text-md md:text-2xl font-bold mb-2">{{ shot.title }}</h3>
                <p class="text-xs md:text-lg opacity-90">{{ shot.desc }}</p>
              </div>
            </div>

            <!-- Arrows -->
            <button @click="prevScreenshot" class="absolute left-4 top-1/2 -translate-y-1/2 w-12 h-12 bg-black/30 hover:bg-black/50 rounded-full flex items-center justify-center text-white backdrop-blur-sm transition-all z-20 opacity-0 group-hover:opacity-100">←</button>
            <button @click="nextScreenshot" class="absolute right-4 top-1/2 -translate-y-1/2 w-12 h-12 bg-black/30 hover:bg-black/50 rounded-full flex items-center justify-center text-white backdrop-blur-sm transition-all z-20 opacity-0 group-hover:opacity-100">→</button>
          </div>

          <!-- Thumbnails/Indicators -->
          <div class="flex justify-center gap-3 mt-8">
            <button v-for="(shot, index) in featureScreenshots" :key="index"
                    @click="activeScreenshotIndex = index"
                    class="h-2 rounded-full transition-all duration-300"
                    :class="index === activeScreenshotIndex ? 'w-8 bg-primary' : 'w-2 bg-gray-300 dark:bg-gray-600 hover:bg-gray-400'"></button>
          </div>
        </div>
      </div>
    </section>

    <!-- 3. Core Features -->
    <section id="core-features" class="py-20 bg-secondary/20 dark:bg-[#1a1a1a]/30">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-16">
          <h2 class="text-3xl font-bold text-neutral-dark dark:text-white mb-4">{{ t.core.title }}</h2>
          <div class="w-16 h-1 bg-primary mx-auto rounded-full"></div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          <div v-for="(feature, index) in features" :key="index" 
               class="bg-white dark:bg-[#141414] rounded-xl p-8 shadow-soft hover:shadow-hover hover:-translate-y-2 transition-all duration-300 border border-transparent hover:border-blue-50 dark:hover:border-blue-900 group">
            <div class="text-5xl mb-6 group-hover:scale-110 transition-transform duration-300">{{ feature.icon }}</div>
            <h3 class="text-2xl font-bold text-neutral-dark dark:text-white mb-4 flex items-center gap-2">
              {{ feature.title }}
              <span v-if="feature.status" :class="['text-xs px-2 py-1 rounded-full font-normal', feature.statusColor]">{{ feature.status }}</span>
            </h3>
            <p class="text-neutral-gray dark:text-gray-400 leading-relaxed mb-6">{{ feature.desc }}</p>
            <div v-if="feature.tags" class="flex flex-wrap gap-2">
              <span v-for="tag in feature.tags" :key="tag" class="text-xs bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-gray-300 px-2 py-1 rounded">{{ tag }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 4. Features Overview -->
    <section id="overview" class="py-20 bg-neutral-light dark:bg-[#141414]/50">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex flex-col lg:flex-row gap-12 lg:gap-20">
          <!-- Left List -->
          <div class="lg:w-[40%]">
            <h2 class="text-2xl md:text-[28px] font-bold text-neutral-dark dark:text-white mb-8 text-center lg:text-left">
              {{ t.overview.title }}
            </h2>
            <div class="space-y-4">
              <div v-for="(item, index) in overviewFeatures" :key="index" 
                   class="bg-white dark:bg-[#141414] rounded-lg p-4 border-l-4 border-primary cursor-pointer transition-all hover:shadow-md"
                   @click="activeFeatureIndex = index">
                <div class="flex justify-between items-center mb-2">
                  <div class="flex items-center gap-3">
                    <span class="text-xl text-primary">{{ item.icon }}</span>
                    <span class="text-lg font-medium text-neutral-dark dark:text-white">{{ item.title }}</span>
                  </div>
                  <span class="transform transition-transform dark:text-gray-400" :class="activeFeatureIndex === index ? 'rotate-180' : ''">⌄</span>
                </div>
                <ul v-show="activeFeatureIndex === index" class="ml-8 space-y-2 mt-2">
                  <li v-for="(subItem, subIndex) in item.items" :key="subIndex" class="text-sm text-neutral-gray dark:text-gray-400 flex items-center gap-2">
                    <div class="w-1.5 h-1.5 rounded-full bg-primary"></div>
                    {{ subItem }}
                  </li>
                </ul>
              </div>
            </div>
          </div>

          <!-- Right Visual -->
          <div class="lg:w-[60%] flex items-center justify-center">
            <div class="bg-white dark:bg-[#141414] rounded-2xl shadow-float p-4 w-full max-w-xl aspect-[4/3] flex items-center justify-center border border-gray-100 dark:border-slate-700 relative overflow-hidden group">
              <div class="text-center">
                <img id="overview-img" :src="overviewFeatures[activeFeatureIndex].image" alt="Feature Image" class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110" loading="eager">
              </div>
              
              <!-- Hover Arrows (Mock) -->
              <div class="absolute left-4 top-1/2 -translate-y-1/2 w-10 h-10 bg-black/30 rounded-full flex items-center justify-center text-white cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity" @click="activeFeatureIndex = (activeFeatureIndex - 1 + overviewFeatures.length) % overviewFeatures.length">←</div>
              <div class="absolute right-4 top-1/2 -translate-y-1/2 w-10 h-10 bg-black/30 rounded-full flex items-center justify-center text-white cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity" @click="activeFeatureIndex = (activeFeatureIndex + 1) % overviewFeatures.length">→</div>
              
              <!-- Dots -->
              <div class="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2">
                <div v-for="(_, i) in overviewFeatures" :key="i" 
                     class="w-2 h-2 rounded-full transition-colors"
                     :class="i === activeFeatureIndex ? 'bg-primary' : 'bg-gray-300 dark:bg-slate-600'"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 5. Agent Skills -->
    <section id="agent-skills" class="py-20 bg-white dark:bg-[#1a1a1a]">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="text-center mb-16">
          <h2 class="text-3xl font-bold text-neutral-dark dark:text-white mb-4">{{ t.agentSkills.title }}</h2>
          <p class="text-neutral-gray dark:text-gray-400 max-w-3xl mx-auto leading-relaxed">{{ t.agentSkills.desc }}</p>
          <div class="w-16 h-1 bg-primary mx-auto rounded-full mt-6"></div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          <div
            v-for="item in t.agentSkills.items"
            :key="item.title"
            class="bg-neutral-light dark:bg-[#141414]/70 rounded-2xl p-8 border border-gray-100 dark:border-slate-700 shadow-soft hover:shadow-hover hover:-translate-y-1 transition-all duration-300"
          >
            <div class="text-4xl mb-5">{{ item.icon }}</div>
            <h3 class="text-xl font-bold text-neutral-dark dark:text-white mb-3">{{ item.title }}</h3>
            <p class="text-sm text-neutral-gray dark:text-gray-300 leading-relaxed mb-5">{{ item.desc }}</p>
            <ul class="space-y-2 text-sm text-neutral-gray dark:text-gray-400">
              <li v-for="ex in item.examples" :key="ex" class="flex gap-2">
                <span class="text-primary">•</span>
                <span class="leading-relaxed">{{ ex }}</span>
              </li>
            </ul>
          </div>
        </div>

        <div class="flex flex-col sm:flex-row justify-center gap-4 mt-12">
          <button class="px-8 py-3 rounded-lg bg-primary text-white font-bold hover:bg-primary-dark hover:scale-105 transition-all shadow-lg hover:shadow-xl" @click="goLink(lang === 'zh-CN' ? '/docs/guide/agent/' : '/en/docs/guide/agent/')">
            {{ t.agentSkills.ctaDocs }}
          </button>
        </div>
      </div>
    </section>

    <!-- 6. Testimonials -->
    <section class="py-20 bg-secondary/30 dark:bg-[#141414]/30">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <h2 class="text-[28px] font-bold text-neutral-dark dark:text-white text-center mb-12">{{ t.testimonials.title }}</h2>
        
        <div class="max-w-3xl mx-auto bg-white dark:bg-[#141414] rounded-xl p-10 shadow-soft relative">
          <!-- Arrows -->
          <button @click="prevTestimonial" class="absolute left-[-20px] md:left-[-50px] top-1/2 -translate-y-1/2 w-10 h-10 bg-black/10 dark:bg-white/10 hover:bg-black/20 dark:hover:bg-white/20 rounded-full flex items-center justify-center text-neutral-dark dark:text-white transition-colors">←</button>
          <button @click="nextTestimonial" class="absolute right-[-20px] md:right-[-50px] top-1/2 -translate-y-1/2 w-10 h-10 bg-black/10 dark:bg-white/10 hover:bg-black/20 dark:hover:bg-white/20 rounded-full flex items-center justify-center text-neutral-dark dark:text-white transition-colors">→</button>

          <div class="text-center">
            <p class="text-lg md:text-xl text-neutral-gray dark:text-gray-300 italic leading-relaxed mb-8">
              "{{ testimonials[testimonialIndex].text }}"
            </p>
            <div class="flex items-center justify-center gap-4">
              <div class="w-12 h-12 bg-gray-200 dark:bg-slate-700 rounded-full flex items-center justify-center text-xl">👤</div>
              <div class="text-left">
                <div class="font-bold text-neutral-dark dark:text-white">{{ testimonials[testimonialIndex].user }}</div>
                <div class="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-slate-700 px-2 py-0.5 rounded-full inline-block mt-1">{{ testimonials[testimonialIndex].role }}</div>
              </div>
            </div>
          </div>

          <!-- Dots -->
          <div class="flex justify-center gap-2 mt-8">
            <div v-for="(_, i) in testimonials" :key="i" 
                 class="w-2 h-2 rounded-full transition-colors cursor-pointer"
                 :class="i === testimonialIndex ? 'bg-primary' : 'bg-gray-300 dark:bg-slate-600'"
                 @click="testimonialIndex = i"></div>
          </div>
        </div>

        <!-- Trust Badges -->
        <div class="text-center mt-16">
          <h3 class="text-base font-bold text-neutral-dark dark:text-white mb-6">{{ t.trust.title }}</h3>
          <div class="flex justify-center gap-10 md:gap-20">
            <div class="flex flex-col items-center gap-2 group cursor-pointer" v-for="(item, index) in t.trust.items" :key="index">
              <div class="text-3xl text-primary group-hover:scale-110 transition-transform">{{ index === 0 ? '🔒' : (index === 1 ? '💾' : '🛡️') }}</div>
              <span class="text-sm text-neutral-gray dark:text-gray-400">{{ item }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 8. Footer -->
    <footer class="bg-neutral-dark dark:bg-[#1a1a1a] text-white pt-16 pb-8">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12 mb-12 text-center md:text-left">
          <!-- Col 1 -->
          <div>
            <h4 class="text-lg font-bold mb-6">{{ t.footer.about.title }}</h4>
            <p class="text-sm opacity-80 leading-relaxed">
              {{ t.footer.about.text }}
            </p>
          </div>
          <!-- Col 2 -->
          <div>
            <h4 class="text-lg font-bold mb-6">{{ t.footer.links.title }}</h4>
            <ul class="space-y-3 text-sm opacity-80">
              <li><a href="#" class="hover:text-primary transition-colors" @click.prevent="goLink(lang === 'zh-CN' ? '/cli' : '/en/cli')">{{ t.footer.links.items[0] }}</a></li>
              <li><a href="#" class="hover:text-primary transition-colors" @click.prevent="scrollTo('core-features')">{{ t.footer.links.items[1] }}</a></li>
              <li><a href="#" class="hover:text-primary transition-colors" @click.prevent="goLink(lang === 'zh-CN' ? '/docs/guide/overview' : '/en/docs/guide/overview')">{{ t.footer.links.items[2] }}</a></li>
              <li><a href="#" class="hover:text-primary transition-colors" @click.prevent="goLink(lang === 'zh-CN' ? '/docs/guide/overview' : '/en/docs/guide/overview')">{{ t.footer.links.items[3] }}</a></li>
              <li><a href="#" class="hover:text-primary transition-colors" @click.prevent="goLink(lang === 'zh-CN' ? '/docs/guide/questions' : '/en/docs/guide/questions')">{{ t.footer.links.items[4] }}</a></li>
            </ul>
          </div>
          <!-- Col 3 -->
          <div>
            <h4 class="text-lg font-bold mb-6">{{ t.footer.contact.title }}</h4>
            <ul class="space-y-3 text-sm text-white/80">
              <li>{{ t.footer.contact.email }}：<a href="mailto:sixyuan044@gmail.com" class="hover:text-primary transition-colors">sixyuan044@gmail.com</a></li>
              <li>{{ t.footer.contact.wechat }}：忆墨痕</li>
              <li class="relative group">
                {{ t.footer.contact.qq }}：
                <span class="cursor-pointer border-b border-dashed border-white/40 hover:text-primary hover:border-primary transition-colors">
                  {{ t.footer.contact.scan }}
                </span>
                <!-- QQ Group QR Code Popup -->
                <div class="absolute bottom-full left-0 mb-2 w-64 bg-white p-2 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-300 z-50 text-neutral-dark">
                  <img src="https://blog.siyuan.ink/static/img/51b2cc72642406a33b42b572203a173c.qq_group.webp" alt="QQ群二维码" class="w-full h-auto rounded" loading="lazy" />
                  <div class="text-xs text-center mt-1 text-black">扫码加入QQ群</div>
                  <!-- Arrow -->
                  <div class="absolute top-full left-4 border-8 border-transparent border-t-white"></div>
                </div>
              </li>
              <li>GitHub：<a href="https://github.com/LC044/TrailSnap" target="_blank" class="cursor-pointer border-b border-dashed border-white/40 hover:text-primary hover:border-primary transition-colors">LC044/TrailSnap</a></li>
            </ul>
          </div>
          <!-- Col 4 -->
          <div>
            <h4 class="text-lg font-bold mb-6">{{ t.footer.follow.title }}</h4>
            <div class="flex justify-center md:justify-start gap-4">
              <div v-for="link in socialLinks" :key="link.name" class="relative group cursor-pointer">
                <!-- Icon -->
                <div class="w-9 h-9 bg-white/10 rounded-full flex items-center justify-center hover:bg-white transition-colors overflow-hidden">
                   <img :src="link.icon" :alt="link.alt" class="w-full h-full object-cover p-1.5 opacity-80 group-hover:opacity-100" />
                </div>
                
                <!-- QR Code Popup -->
                <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-32 bg-white p-2 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-300 z-50 text-neutral-dark">
                  <img :src="link.qrCode" :alt="link.alt + ' QR'" class="w-full h-auto rounded" />
                  <div class="text-xs text-center mt-1 text-black">{{ link.alt }}</div>
                  <!-- Arrow -->
                  <div class="absolute top-full left-1/2 -translate-x-1/2 border-8 border-transparent border-t-white"></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="border-t border-white/10 pt-8 text-center">
          <p class="text-xs opacity-60">
            {{ t.footer.copyright }} <span class="mx-2">|</span> {{ t.footer.privacy }} <span class="mx-2">|</span> {{ t.footer.agreement }}
          </p>
        </div>
      </div>
    </footer>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter, useData } from 'vitepress'

const router = useRouter()
const { lang } = useData()

// Translations
const i18n = {
  'zh-CN': {
    nav: {
      home: '首页',
      features: '功能介绍',
      quickStart: '快速开始',
      download: '立即体验'
    },
    hero: {
      title1: 'AI赋能家庭相册',
      title2: '你的专属行影集',
      desc: 'AI智能分析、整理相册照片、生成专属记忆报告，<br class="hidden md:inline">让每一段出行都值得珍藏',
      tags: ['AI相册', '足迹相册', '故事相册'],
      download: '快速开始',
      details: '查看功能详情',
      chat: {
        online: '在线',
        userMsg: '我去年国庆去哪玩了，帮我整理一个旅游攻略，我准备发一个小红书',
        aiMsg1: '从你的照片足迹来看，去年国庆（2025年10月）你进行了一场超级丰富的旅行！🏔️🌊🏙️',
        itineraryTitle: '国庆旅行足迹',
        itinerary: [
          { date: '10月1日', desc: '湖州、苏州（苏州园林）' },
          { date: '10月2日', desc: '黄山、徽州古城' },
          { date: '10月3日', desc: '景德镇' },
          { date: '10月4日', desc: '金华、衢州' },
          { date: '10月5日', desc: '宁波、舟山' },
          { date: '10月6-7日', desc: '上海' }
        ],
        photoTitle: '精选旅行照片',
        copyTitle: '小红书文案建议',
        copyTitleText: '《国庆7天，9城打卡！我的旅行清单太丰富了😭》',
        copyBody: [
          '开头：分享国庆旅行的喜悦',
          '中间：按时间线介绍每个城市亮点',
          '结尾：附上实用Tips（住宿、交通等）'
        ],
        questionIntro: '不过，由于每张照片的具体描述信息有限，<strong class="text-neutral-dark dark:text-gray-200">你想针对哪个城市或景点写更详细的攻略呢？</strong> 比如：',
        questionOptions: [
          { icon: '🏯', name: '苏州园林', desc: '园林建筑、拍照机位' },
          { icon: '⛰️', name: '徽州古城', desc: '古村落、徽派建筑' },
          { icon: '🏮', name: '景德镇', desc: '陶瓷文化、窑址体验' },
          { icon: '🌊', name: '舟山', desc: '海岛风光、港口夜景' }
        ],
        questionOutro: '告诉我你重点想写哪个地方，我可以帮你整理更详细的攻略内容！✨'
      }
    },
    screenshots: {
      title: '功能展示'
    },
    core: {
      title: '核心特色 · 重新定义相册记忆'
    },
    overview: {
      title: '功能概览 · 全方位覆盖智能化需求',
      demoSuffix: ' 演示',
      demoPlaceholder: '（此处展示功能演示动图/视频）'
    },
    agentSkills: {
      title: 'Agent Skills · AI 能帮你做什么',
      desc: '把 TrailSnap 变成 AI 的“个人知识库”。Agent 通过 Skill 直接查询你的相册数据，帮你检索、总结、生成内容。',
      ctaDocs: '查看使用文档',
      ctaToken: '获取 Token',
      items: [
        {
          icon: '🔎',
          title: '智能检索相册',
          desc: '用自然语言查询照片、人物、地点、标签等信息，支持组合筛选。',
          examples: ['最近在西安拍的照片有哪些？', '帮我找出包含“登机口”文字的照片']
        },
        {
          icon: '📝',
          title: '生成游记/文案',
          desc: '基于足迹与照片内容，自动整理时间线与亮点，生成可发布的内容。',
          examples: ['我去年国庆节去了哪些地方？', '帮我写一篇 HTML 格式旅行日记']
        },
        {
          icon: '🧰',
          title: '自动化工作流',
          desc: '把 CLI 当工具接入 Claude Code / OpenClaw 等，让 AI 执行可重复的查询与整理任务。',
          examples: ['列出最近 50 张照片的拍摄地点统计', '按城市导出一份相册清单']
        }
      ]
    },
    testimonials: {
      title: '用户心声 · 用行影集珍藏每一段旅程'
    },
    trust: {
      title: '安全保障 · 数据真正属于你',
      items: ['全链路数据掌控', '本地存储', '隐私保护']
    },
    footer: {
      about: { title: '关于行影集', text: 'TrailSnap行影集是一款AI赋能的出行记忆珍藏工具，致力于让每一段出行都值得回味，让用户的数据真正属于自己。' },
      links: { title: '快速链接', items: ['TrialSnap CLI', '功能介绍', '产品优势', '关于我们', '帮助中心'] },
      contact: { title: '联系我们', email: '邮箱', wechat: '微信公众号', qq: 'QQ群', scan: '扫码加入' },
      follow: { title: '关注我们' },
      copyright: '© 2025 TrailSnap行影集 版权所有',
      privacy: '隐私政策',
      agreement: '用户协议'
    }
  },
  'en-US': {
    nav: {
      home: 'Home',
      features: 'Features',
      quickStart: 'Quick Start',
      download: 'Download'
    },
    hero: {
      title1: 'AI-Empowered Travel Memories',
      title2: 'Your Exclusive TrailSnap',
      desc: 'Smartly record itineraries, organize travel photos, generate exclusive memory reports, <br class="hidden md:inline">making every trip worth cherishing.',
      tags: ['AI Album', 'Footprint Album', 'Story Album'],
      download: 'Download',
      details: 'View Features',
      chat: {
        online: 'Online',
        userMsg: 'Where did I travel last National Day? Help me organize a travel guide for a social media post.',
        aiMsg1: 'Based on your photo footprints, you had a super rich trip last National Day (Oct 2025)! 🏔️🌊🏙️',
        itineraryTitle: 'National Day Itinerary',
        itinerary: [
          { date: 'Oct 1', desc: 'Huzhou, Suzhou (Gardens)' },
          { date: 'Oct 2', desc: 'Huangshan, Huizhou Ancient City' },
          { date: 'Oct 3', desc: 'Jingdezhen' },
          { date: 'Oct 4', desc: 'Jinhua, Quzhou' },
          { date: 'Oct 5', desc: 'Ningbo, Zhoushan' },
          { date: 'Oct 6-7', desc: 'Shanghai' }
        ],
        photoTitle: 'Selected Travel Photos',
        copyTitle: 'Xiaohongshu Copy Suggestions',
        copyTitleText: '"7 Days, 9 Cities! My National Day Trip was Insane 😭"',
        copyBody: [
          'Intro: Share the joy of the trip',
          'Body: Highlight each city chronologically',
          'Outro: Add practical tips (hotels, transport, etc.)'
        ],
        questionIntro: 'However, since photo details are limited, <strong class="text-neutral-dark dark:text-gray-200">which city/spot do you want a more detailed guide for?</strong> For example:',
        questionOptions: [
          { icon: '🏯', name: 'Suzhou Gardens', desc: 'Architecture, photo spots' },
          { icon: '⛰️', name: 'Huizhou City', desc: 'Ancient villages, Hui architecture' },
          { icon: '🏮', name: 'Jingdezhen', desc: 'Ceramic culture, kiln experience' },
          { icon: '🌊', name: 'Zhoushan', desc: 'Island scenery, port night view' }
        ],
        questionOutro: 'Tell me where you want to focus, and I\'ll organize a detailed guide for you! ✨'
      }
    },
    screenshots: {
      title: 'Feature Screenshots'
    },
    core: {
      title: 'Core Features · Redefining Memories'
    },
    overview: {
      title: 'Feature Overview · Comprehensive Coverage',
      demoSuffix: ' Demo',
      demoPlaceholder: '(Feature demo GIF/Video here)'
    },
    agentSkills: {
      title: 'Agent Skills · What AI can do',
      desc: 'Turn TrailSnap into your personal knowledge base. With Skills, an Agent can query your album data and help you search, summarize, and generate content.',
      ctaDocs: 'View Docs',
      ctaToken: 'Get Token',
      items: [
        {
          icon: '🔎',
          title: 'Search your album',
          desc: 'Query photos, people, locations, and tags with natural language and combined filters.',
          examples: ['List my recent photos taken in Xi’an', 'Find photos that contain “boarding gate” text']
        },
        {
          icon: '📝',
          title: 'Generate diaries & copy',
          desc: 'Summarize footprints and photo content into timelines, highlights, and publishable posts.',
          examples: ['Where did I travel last National Day?', 'Generate an HTML travel diary for me']
        },
        {
          icon: '🧰',
          title: 'Automate workflows',
          desc: 'Connect the CLI as a tool in Claude Code / OpenClaw and let AI run repeatable tasks for you.',
          examples: ['Summarize locations for my last 50 photos', 'Export a city-based album list']
        }
      ]
    },
    testimonials: {
      title: 'User Voice · Cherish Every Journey'
    },
    trust: {
      title: 'Security · Your Data Truly Belongs to You',
      items: ['Full Data Control', 'Local Storage', 'Privacy Protection']
    },
    footer: {
      about: { title: 'About TrailSnap', text: 'TrailSnap is an AI-powered travel memory tool, dedicated to making every trip memorable and ensuring your data belongs to you.' },
      links: { title: 'Quick Links', items: ['TrailSnap CLI', 'Features', 'Advantages', 'About Us', 'Help Center'] },
      contact: { title: 'Contact Us', email: 'Email', wechat: 'WeChat', qq: 'QQ Group', scan: 'Scan to Join' },
      follow: { title: 'Follow Us' },
      copyright: '© 2025 TrailSnap All Rights Reserved',
      privacy: 'Privacy Policy',
      agreement: 'User Agreement'
    }
  }
}

const t = computed(() => i18n[lang.value as keyof typeof i18n] || i18n['zh-CN'])

const featureScreenshotsList = {
  'zh-CN': [
    { title: 'AI时光旁白', desc: '大模型分析照片内容，对每张图进行评分和总结，精准推送那年今日值得回忆的照片', image: 'https://blog.siyuan.ink/static/img/f811e803accb19fac75d25aee85d6fef.b9c6733fd2043b5fd7c908099c5e1ec5.webp' },
    { title: '地图模式', desc: '在地图上查看您的足迹，点亮每一个去过的城市', image: 'https://blog.siyuan.ink/static/img/38bd45b7c69fe79457e74109dbba8683.map.webp' },
    { title: '智能分类', desc: '自动识别照片中的人物、景物，智能归类', image: 'https://blog.siyuan.ink/static/img/8082f0451f051b1ad848b9c4261359e7.classification.webp'},
    { title: '时光轴展示', desc: '丝滑的时间轴滚动效果', image: 'https://blog.siyuan.ink/static/img/7f3995c1fa22ded5a26506194a516da4.timeline.webp' }
  ],
  'en-US': [
    { title: 'Timeline View', desc: 'Smooth timeline scrolling effect', image: '' },
    { title: 'Map Mode', desc: 'View your footprints on the map and light up every city you visited', image: '' },
    { title: 'Smart Classification', desc: 'Automatically identify people and scenery in photos and classify them intelligently', image: '' }
  ]
}

const featureScreenshots = computed(() => featureScreenshotsList[lang.value as keyof typeof featureScreenshotsList] || featureScreenshotsList['zh-CN'])
const activeScreenshotIndex = ref(0)

const nextScreenshot = () => {
  activeScreenshotIndex.value = (activeScreenshotIndex.value + 1) % featureScreenshots.value.length
}

const prevScreenshot = () => {
  activeScreenshotIndex.value = (activeScreenshotIndex.value - 1 + featureScreenshots.value.length) % featureScreenshots.value.length
}

const featuresList = {
  'zh-CN': [
      {
    title: '智能相册',
    icon: '📸',
    desc: '人物识别、场景智能分类、智能搜索、足迹相册、照片OCR识别，轻松找到每一张旅行照片。',
    tags: ['人物识别', '智能分类', 'OCR识别']
  },
  {
    title: '行程记录',
    icon: '🎫',
    desc: '专属火车票、景区门票、演唱会门票管理功能，自动识别票据信息，识别国内5A级景区，清晰回顾每一段出行轨迹。',
    status: '开发中',
    tags: ['智能识别', '行程管理', '旅行足迹'],
    statusColor: 'bg-orange-100 text-orange-600'
  },
  {
    title: 'AI赋能',
    icon: '🤖',
    desc: 'AI给每张照片多维度评分，智能清理低质量照片；一句话生成旅行日记，自动剪辑15s旅行Vlog，智能修图筛选高质量照片，轻松打造专属旅行分享内容。',
    status: '开发中',
    statusColor: 'bg-blue-100 text-blue-600'
  }
  ],
  'en-US': [
    {
    title: 'Smart Album',
    icon: '📸',
    desc: 'Face recognition, smart scene classification, smart search, footprint album, photo OCR, easily find every travel photo.',
    tags: ['Face Recognition', 'Smart Classification', 'OCR']
  },
  {
    title: 'Itinerary Record',
    icon: '🎫',
    desc: 'Exclusive management for train tickets, scenic spot tickets, concert tickets, automatic ticket info recognition, 5A scenic spot recognition.',
    status: 'In Dev',
    tags: ['Smart Recognition', 'Itinerary Mgmt', 'Travel Footprint'],
    statusColor: 'bg-orange-100 text-orange-600'
  },
  {
    title: 'AI Empowerment',
    icon: '🤖',
    desc: 'One-sentence travel diary generation, auto-edit 15s travel Vlog, smart photo retouching and selection.',
    status: 'Planned',
    statusColor: 'bg-blue-100 text-blue-600'
  }
  ]
}

const features = computed(() => featuresList[lang.value as keyof typeof featuresList] || featuresList['zh-CN'])

const overviewFeaturesList = {
  'zh-CN': [
    { title: '智能相册', icon: '📸', items: ['精准人脸识别归类', '场景/物体智能标签', '自定义条件（智能）相册'], image: 'https://blog.siyuan.ink/static/img/8082f0451f051b1ad848b9c4261359e7.classification.webp' },
    { title: 'AI能力', icon: '🤖', items: ['一句话生成游记', 'Vlog智能剪辑', '照片智能精修'], image: '/images/ScreenShot_2026-05-09_005142_617.png' },
    { title: '行程票据', icon: '🎫', items: ['票据自动识别录入', '国内5A景区位置识别', '多票据统一管理'], image: '/images/火车票_郑州东_天津西_G1710_2026-12-12.png' },
    { title: '数据可视化', icon: '📊', items: ['足迹地图点亮', '出行里程统计', '城市打卡记录'], image: 'https://blog.siyuan.ink/static/img/fc209e02f7046645cb38bd6dead5d088.map-province.webp' },
    { title: '年度报告', icon: '📅', items: ['年度出行总结', '专属回忆生成', '分享朋友圈'], image: 'https://blog.siyuan.ink/static/img/720c50509ca349f40b1e8038371b7bcf.å¹´åº¦æ¥å.webp' },
    { title: '工具箱', icon: '🧰', items: ['照片一键整理', '照片元数据修复', '低质量清理'], image: '/images/toolbox.jpg' }
  ],
  'en-US': [
    { title: 'Smart Album', icon: '📸', items: ['Precise Face Clustering', 'Scene/Object Smart Tags', 'Custom Smart Albums'], image: 'https://blog.siyuan.ink/static/img/8082f0451f051b1ad848b9c4261359e7.classification.webp' },
    { title: 'AI Capabilities', icon: '🤖', items: ['One-sentence Diary', 'Smart Vlog Editing', 'Smart Photo Retouching'], image: 'https://blog.siyuan.ink/static/img/943063875ecd4ff82543e0ae3a21a4a4.AI-narrative.webp' },
    { title: 'Itinerary & Tickets', icon: '🎫', items: ['Auto Ticket Recognition', '5A Scenic Spot Location', 'Unified Ticket Mgmt'], image: 'https://blog.siyuan.ink/static/img/38bd45b7c69fe79457e74109dbba8683.map.webp' },
    { title: 'Data Visualization', icon: '📊', items: ['Footprint Map Lighting', 'Travel Mileage Stats', 'City Check-in Records'], image: 'https://blog.siyuan.ink/static/img/fc209e02f7046645cb38bd6dead5d088.map-province.webp' },
    { title: 'Annual Report', icon: '📅', items: ['Annual Travel Summary', 'Exclusive Memory Gen', 'Share to Moments'], image: 'https://blog.siyuan.ink/static/img/720c50509ca349f40b1e8038371b7bcf.å¹´åº¦æ¥å.webp' },
    { title: 'Toolbox', icon: '🧰', items: ['Batch Image Processing', 'Photo Metadata Management', 'Data Backup & Restore'], image: '/images/toolbox.jpg' }
  ]
}

const overviewFeatures = computed(() => overviewFeaturesList[lang.value as keyof typeof overviewFeaturesList] || overviewFeaturesList['zh-CN'])

const testimonialsList = {
  'zh-CN': [
    {
    text: '每次旅行拍的照片都乱七八糟，用了行影集后自动分类，还能识别车票生成行程，年底的年度报告更是惊喜，满满的回忆！',
    user: '旅行爱好者小A',
    role: '行影集内测用户'
  },
  {
    text: '最喜欢它的AI功能，自动剪辑的Vlog非常有感觉，省去了我大量剪辑视频的时间，强烈推荐给喜欢记录生活的朋友。',
    user: '摄影师大白',
    role: '资深用户'
  }
  ],
  'en-US': [
    {
    text: 'My travel photos used to be a mess. TrailSnap sorted them automatically and even generated itineraries from tickets. The annual report was a huge surprise!',
    user: 'Travel Enthusiast A',
    role: 'Beta User'
  },
  {
    text: 'I love the AI features the most. The auto-edited Vlog has great vibes and saved me tons of time. Highly recommended for life recorders.',
    user: 'Photographer Baymax',
    role: 'Power User'
  }
  ]
}

const testimonials = computed(() => testimonialsList[lang.value as keyof typeof testimonialsList] || testimonialsList['zh-CN'])

const isMobileMenuOpen = ref(false)
const isScrolled = ref(false)
const activeSection = ref<'home' | 'core-features'>('home')

// Carousel State
const activeFeatureIndex = ref(0)
const testimonialIndex = ref(0)

const toggleMobileMenu = () => {
  isMobileMenuOpen.value = !isMobileMenuOpen.value
}

const handleScroll = () => {
  isScrolled.value = window.scrollY > 50
}

onMounted(() => {
  window.addEventListener('scroll', handleScroll)

  // Preload overview images when section is visible
  const overviewSection = document.getElementById('overview')
  if (overviewSection) {
    const imgObserver = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting) {
          overviewFeatures.value.forEach(f => {
            const img = new Image()
            img.src = f.image
          })
          imgObserver.disconnect()
        }
      },
      { threshold: 0.1 }
    )
    imgObserver.observe(overviewSection)
  }

  const ids = ['home', 'core-features']
  const els = ids
    .map(id => document.getElementById(id))
    .filter((el): el is HTMLElement => Boolean(el))

  const io = new IntersectionObserver(
    entries => {
      const visible = entries
        .filter(e => e.isIntersecting)
        .sort((a, b) => (b.intersectionRatio ?? 0) - (a.intersectionRatio ?? 0))[0]
      if (!visible?.target?.id) return
      if (visible.target.id === 'home' || visible.target.id === 'core-features') {
        activeSection.value = visible.target.id
      }
    },
    { root: null, threshold: [0.15, 0.25, 0.4], rootMargin: '-20% 0px -60% 0px' }
  )

  els.forEach(el => io.observe(el))

  onUnmounted(() => {
    io.disconnect()
  })
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
})

const goLink = (path: string) => {
  router.go(path)
  isMobileMenuOpen.value = false
}

const scrollTo = (id: 'home' | 'core-features') => {
  const el = document.getElementById(id)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  isMobileMenuOpen.value = false
}

const navClass = (id: 'home' | 'core-features') => {
  const base = 'text-neutral-dark dark:text-gray-300 hover:text-primary'
  if (activeSection.value !== id) return base
  return 'text-primary font-medium border-b-2 border-primary'
}

const socialLinks = [
  {
    name: 'WeChat',
    icon: '/icons/wechat.svg',
    qrCode: '/qrcodes/wechat_qr.jpg',
    alt: '微信公众号'
  },
  {
    name: 'RedBook',
    icon: '/icons/xiaohongshu.svg',
    qrCode: '/qrcodes/xiaohongshu_qr.jpg',
    alt: '小红书'
  },
  {
    name: 'Bilibili',
    icon: '/icons/bilibili.svg',
    qrCode: '/qrcodes/bilibili_qr.jpg',
    alt: 'B站'
  }
]

const nextTestimonial = () => {
  testimonialIndex.value = (testimonialIndex.value + 1) % testimonials.value.length
}

const prevTestimonial = () => {
  testimonialIndex.value = (testimonialIndex.value - 1 + testimonials.value.length) % testimonials.value.length
}

</script>
<style scoped>
@keyframes float {
  0% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
  100% { transform: translateY(0); }
}

.animate-float {
  animation: float 4s ease-in-out infinite;
}

@keyframes float-slow {
  0% { transform: translateY(0); }
  50% { transform: translateY(-15px); }
  100% { transform: translateY(0); }
}

.animate-float-slow {
  animation: float-slow 6s ease-in-out infinite;
}

@keyframes fade-in-up {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.animate-fade-in-up {
  animation: fade-in-up 0.6s ease-out forwards;
}

/* Typing effect */
.typing-container p, .typing-container li {
  overflow: hidden;
  opacity: 0;
  animation: reveal-text 0.1s forwards;
}

@keyframes reveal-text {
  to { opacity: 1; }
}

/* Add delays for typing effect */
.typing-container > p:nth-child(1) { animation-delay: 0.5s; }
.typing-container > div:nth-child(2) p { animation-delay: 1.0s; }
.typing-container > div:nth-child(2) li:nth-child(1) { animation-delay: 1.2s; }
.typing-container > div:nth-child(2) li:nth-child(2) { animation-delay: 1.3s; }
.typing-container > div:nth-child(2) li:nth-child(3) { animation-delay: 1.4s; }
.typing-container > div:nth-child(2) li:nth-child(4) { animation-delay: 1.5s; }
.typing-container > div:nth-child(2) li:nth-child(5) { animation-delay: 1.6s; }
.typing-container > div:nth-child(2) li:nth-child(6) { animation-delay: 1.7s; }

.typing-container > div:nth-child(3) p { animation-delay: 2.0s; }

.thumbnails-container {
  opacity: 0;
  animation: fade-in-up 0.5s ease-out forwards;
  animation-delay: 2.2s;
}

.typing-container > div:nth-child(4) p:nth-child(1) { animation-delay: 2.5s; }
.typing-container > div:nth-child(4) p:nth-child(2) { animation-delay: 2.7s; }
.typing-container > div:nth-child(4) p:nth-child(3) { animation-delay: 2.9s; }
.typing-container > div:nth-child(4) li:nth-child(1) { animation-delay: 3.1s; }
.typing-container > div:nth-child(4) li:nth-child(2) { animation-delay: 3.3s; }
.typing-container > div:nth-child(4) li:nth-child(3) { animation-delay: 3.5s; }

.typing-container > div:nth-child(5) p:nth-child(1) { animation-delay: 3.8s; }
.typing-container > div:nth-child(5) li:nth-child(1) { animation-delay: 4.0s; }
.typing-container > div:nth-child(5) li:nth-child(2) { animation-delay: 4.2s; }
.typing-container > div:nth-child(5) li:nth-child(3) { animation-delay: 4.4s; }
.typing-container > div:nth-child(5) li:nth-child(4) { animation-delay: 4.6s; }
.typing-container > div:nth-child(5) p:nth-child(3) { animation-delay: 4.8s; }

/* Custom Scrollbar for Chat Window */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.5); /* gray-400 with opacity */
  border-radius: 10px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background-color: rgba(107, 114, 128, 0.8); /* gray-500 with opacity */
}

/* Firefox scrollbar support */
.custom-scrollbar {
  scrollbar-width: thin;
  scrollbar-color: rgba(156, 163, 175, 0.5) transparent;
}

html.dark .custom-scrollbar {
  scrollbar-color: rgba(75, 85, 99, 0.5) transparent;
}

html.dark .custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(75, 85, 99, 0.5); /* gray-600 with opacity */
}

html.dark .custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background-color: rgba(107, 114, 128, 0.8); /* gray-500 with opacity */
}
</style>

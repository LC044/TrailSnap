<template>
  <ReportPage class="section-photo-wall w-full max-w-screen max-h-full" :class="{ 'animate-in': isVisible }" ref="sectionRef" :max-width="'max'">
    <div class="relative w-full h-full overflow-hidden perspective-container snap-start"
        @mousedown="handleMouseDown"
        @mousemove="handleMouseMove"
        @touchstart="handleMouseDown"
        @touchmove="handleMouseMove"
        @click="togglePause">

        <div v-if="loading" class="absolute inset-0 flex items-center justify-center">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-amber"></div>
        </div>

        <div v-else
            class="scene w-full h-full absolute top-0 left-0 flex items-center justify-center transform-style-3d"
            :style="getSceneStyle">
            <div v-for="(photo, index) in photos"
                :key="index"
                :ref="(el) => setPhotoRef(el, index)"
                class="photo-card absolute bg-white dark:bg-gray-800 p-1 shadow-lg rounded-sm overflow-hidden cursor-pointer hover:scale-110 hover:z-[9999]"
                :style="{
                    width: isMobile ? '60px' : '80px',
                    height: isMobile ? '45px' : '60px',
                    ...getPhotoStyle(index),
                }">
                <!-- Fixed size for simplicity in 3D, could be responsive -->
                <img :src="getPhotoUrl(photo)"
                    class="w-full h-full object-cover"
                    loading="lazy"
                    alt="Memory" />
            </div>
        </div>

        <!-- Controls / Hints -->
        <div v-if="currentStage === 4" class="absolute bottom-10 left-1/2 transform -translate-x-1/2 text-white/50 text-sm bg-black/20 px-4 py-1 rounded-full backdrop-blur-sm pointer-events-none">
            {{ isPaused ? '已暂停' : '点击暂停/继续' }}
        </div>
    </div>
  </ReportPage>
</template>


<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted, watch } from 'vue';
import { getAnnualReportPhotos } from '@/api/annualReport';
import ReportPage from './ReportPage.vue';
import type { Photo } from '@/types/album';
import { useWindowSize } from '@vueuse/core';

const props = defineProps<{
  startTime: string;
  endTime: string;
}>();

import { useIntersectionObserver } from '@vueuse/core';
import { toServerUrl } from '@/config/server';
import { thumbnailUrl } from '@/utils/mediaUrl';
const isVisible = ref(false);
const sectionRef = ref<HTMLElement | null>(null);

useIntersectionObserver(
    sectionRef,
    ([{ isIntersecting }]) => {
        if (isIntersecting && !isVisible.value) {
            console.log(isVisible)
            isVisible.value = true;
        }
    },
    { threshold: 0.1 }
);

// 监听 isVisible 触发动画
watch(isVisible, (newVal) => {
  if (newVal) {
    startAnimationSequence();
  }
});

const { width: windowWidth, height: windowHeight } = useWindowSize();

// State
const rootEl = ref<HTMLElement | null>(null);
const photos = ref<Photo[]>([]);
const photoRefs = ref<(HTMLElement | null)[]>([]);
const loading = ref(true);
const currentStage = ref(0); // 0: Init, 1: FlyIn, 2: Shape, 3: Grid, 4: Scroll
const scrollOffset = ref(0);
const isPaused = ref(false);
const hasStartedAnimation = ref(false);
let animationFrameId: number;

const isMobile = computed(() => windowWidth.value < 768);

const setPhotoRef = (el: any, index: number) => {
    photoRefs.value[index] = el as HTMLElement;
};

// Constants
const MAX_PHOTOS = 500;
const PHOTOS_PER_MONTH = 10;

// Photo positions for different stages
const positions = ref<{ x: number; y: number; z: number; rX: number; rY: number; rZ: number; scale: number; opacity: number; width?: number; height?: number }[]>([]);

const getPhotoUrl = (photo: Photo) => {
    return thumbnailUrl(photo.id, 'small', photo.owner_id);
    return `https://picsum.photos/seed/${photo.id}/400/600`;
}

// Fetch Photos
const fetchPhotos = async () => {
  try {
    const start = props.startTime;
    const end = props.endTime;

    const monthlyGroups = await getAnnualReportPhotos(start, end);

    // Flatten and sort
    let list: Photo[] = [];
    Object.values(monthlyGroups).forEach(group => list.push(...group));
    list.sort((a, b) => {
        const tA = new Date(a.photo_time || a.upload_time).getTime();
        const tB = new Date(b.photo_time || b.upload_time).getTime();
        return tB - tA;
    });

    if (list.length > MAX_PHOTOS) list = list.slice(0, MAX_PHOTOS);

    // Duplication Logic for Infinite Scroll
    // Ensure we have enough photos to fill the screen width multiple times for smooth scrolling
    // Target: at least 150 items or enough to fill 7 rows x 20 items
    const MIN_ITEMS_FOR_SCROLL = 150;
    if (list.length > 0 && list.length < MIN_ITEMS_FOR_SCROLL) {
        const originalList = [...list];
        let dupCount = 0;
        while (list.length < MIN_ITEMS_FOR_SCROLL) {
            dupCount++;
            list.push(...originalList.map(p => ({
                ...p,
            })));
        }
        // Cap again just in case
        if (list.length > MAX_PHOTOS) list = list.slice(0, MAX_PHOTOS);
    }

    photos.value = list;
    
    // Initialize positions
    initPositions(list.length);

    loading.value = false;

    // Check if we should start animation (if already visible)
    // checkVisibilityAndAnimate();

  } catch (e) {
    console.error("Failed to fetch photos for wall", e);
    loading.value = false;
  }
};

const initPositions = (count: number) => {
  const newPositions = [];
  for (let i = 0; i < count; i++) {
    // Initial: Offscreen random
    newPositions.push({
      x: (Math.random() - 0.5) * windowWidth.value * 3,
      y: (Math.random() - 0.5) * windowHeight.value * 3,
      z: 1000 + Math.random() * 1000,
      rX: Math.random() * 360,
      rY: Math.random() * 360,
      rZ: Math.random() * 360,
      scale: 0,
      opacity: 0
    });
  }
  positions.value = newPositions;
};

// Animation Sequence
const startAnimationSequence = async () => {
    // Wait a bit for render
    // await new Promise(r => setTimeout(r, 100));

    // Stage 1: Fly In (Random Scatter on screen)
    currentStage.value = 1;
    updatePositionsForStage1();

    // Wait for fly-in (3.5s) + hold
    setTimeout(() => {
        // Stage 2: Shape (Sphere)
        currentStage.value = 2;
        updatePositionsForStage2();

        // Auto-rotate sphere during Stage 2
        const rotateInterval = setInterval(() => {
            if (currentStage.value !== 2) {
                clearInterval(rotateInterval);
                return;
            }
            if (!isDragging.value) {
                sphereRotation.value.y += 0.2;
            }
        }, 16);

        setTimeout(() => {
            // Stage 3: Grid
            currentStage.value = 3;
            clearInterval(rotateInterval);
            updatePositionsForStage3();

            setTimeout(() => {
                // Stage 4: Scroll
                currentStage.value = 4;
                startScrollLoop();
            }, 2000); // Wait 2s after grid

        }, 5500); // Shape hold 4s + transition 1.5s
    }, 3500); // Fly in 3.5s
};

const updatePositionsForStage1 = () => {
    // Random scatter within view
    positions.value = positions.value.map((_, i) => ({
        x: (Math.random() - 0.5) * windowWidth.value * 0.8,
        y: (Math.random() - 0.5) * windowHeight.value * 0.8,
        z: (Math.random() - 0.5) * 500,
        rX: (Math.random() - 0.5) * 30, // -15 to 15
        rY: (Math.random() - 0.5) * 30,
        rZ: (Math.random() - 0.5) * 30,
        scale: 0.5 + Math.random() * 0.5, // 0.5 to 1
        opacity: 1
    }));
};

const updatePositionsForStage2 = () => {
    // Sphere
    const count = positions.value.length;

    // Optimization: Limit visible photos in Sphere to avoid clutter and performance issues
    const isMobile = windowWidth.value < 768;
    const maxSphereItems = isMobile ? 60 : 120; // Reduced count for better visuals
    const sphereRadius = Math.min(windowWidth.value, windowHeight.value) * (isMobile ? 0.4 : 0.35);
    const photoSize = isMobile ? { w: 100, h: 75 } : { w: 160, h: 120 };

    // Use Golden Spiral for even distribution
    // Only map the first 'maxSphereItems', hide others

    // Recalculate golden angle for the subset to ensure the sphere is complete
    // If we just take first N of M, and M is large, it's fine.
    // But we need to make sure we distribute N items over the sphere surface.

    const phi = Math.PI * (3 - Math.sqrt(5)); // Golden angle

    positions.value = positions.value.map((_, i) => {
        if (i >= maxSphereItems) {
            // Hide excess photos
            return {
                x: 0, y: 0, z: 0, rX: 0, rY: 0, rZ: 0, scale: 0, opacity: 0,
                width: photoSize.w, height: photoSize.h
            };
        }

        const y = 1 - (i / (maxSphereItems - 1)) * 2; // y goes from 1 to -1
        const r = Math.sqrt(1 - y * y); // Radius at y
        const theta = phi * i; // Golden angle increment

        const x = Math.cos(theta) * r;
        const z = Math.sin(theta) * r;

        return {
            x: x * sphereRadius,
            y: y * sphereRadius,
            z: z * sphereRadius,
            rX: 0,
            rY: theta * (180 / Math.PI), // Face outwards approx
            rZ: 0,
            scale: 1,
            opacity: 1,
            width: photoSize.w,
            height: photoSize.h
        };
    });
};

const updatePositionsForStage3 = () => {
    // Staggered Grid with Horizontal Scroll preparation
    const count = positions.value.length;

    // Determine rows based on screen height
    let rows = 7;
    if (windowHeight.value < 600) rows = 5;
    else if (windowHeight.value < 900) rows = 7; // Force odd rows for symmetry

    const gap = 4; // Compact gap

    // Calculate heights
    // We want middle row to be larger (e.g. 1.5x)
    // Formula: (rows - 1) * h + 1.5 * h + (rows + 1) * gap = H_screen
    // (rows + 0.5) * h = H_screen - (rows + 1) * gap
    const baseHeight = (windowHeight.value - (rows + 1) * gap) / (rows + 0.6);
    const largeHeight = baseHeight * 1.5;
    const midRowIndex = Math.floor(rows / 2);

    // Calculate row configurations (Y position, Height)
    const rowConfigs: { y: number, height: number, width: number }[] = [];
    let currentY = -windowHeight.value / 2 + gap;

    for (let r = 0; r < rows; r++) {
        const isMid = r === midRowIndex;
        const h = isMid ? largeHeight : baseHeight;
        // Center the item in its slot
        const y = currentY + h / 2;
        currentY += h + gap;
        rowConfigs.push({
            y,
            height: h,
            width: h * (4 / 3) // 4:3 Aspect Ratio
        });
    }

    // Distribute photos
    // Ensure even distribution across rows to prevent gaps
    const rowItemsIndices: number[][] = Array.from({ length: rows }, () => []);
    positions.value.forEach((_, i) => {
        rowItemsIndices[i % rows].push(i);
    });

    // We clone positions to update them
    const newPositions = [...positions.value];

    rowItemsIndices.forEach((indices, rowIndex) => {
        const config = rowConfigs[rowIndex];
        const countInRow = indices.length;
        const totalRowWidth = countInRow * (config.width + gap);
        // Center the row initially
        const startX = -totalRowWidth / 2;
        indices.forEach((posIndex, colIndex) => {
             // Calculate x: Start from left + center offset for item
             const x = startX + colIndex * (config.width + gap) + config.width / 2;
             newPositions[posIndex] = {
                x: x,
                y: config.y,
                z: 0,
                rX: 0,
                rY: 0,
                rZ: 0,
                scale: 1,
                opacity: 1,
                width: config.width,
                height: config.height,
                // Store loop info in the object for the scroll loop to use
                // We add it as a custom property (need to cast or extend type if strict, but for now JS logic holds)
                loopLength: totalRowWidth,
                rowWidth: config.width
             } as any;
        });
    });
    
    positions.value = newPositions;
};

// Scroll Loop
const startScrollLoop = () => {
    // Optimization: Use non-reactive positions for loop to avoid Vue overhead
    const currentPositions = positions.value.map(p => ({ ...p }));
    
    // We rely on the loop info stored in Stage 3
    const loop = () => {
        if (!isPaused.value && currentStage.value === 4) {
             currentPositions.forEach((p, i) => {
                 p.x -= 0.8; // Horizontal Scroll speed

                 const loopLength = (p as any).loopLength;
                 const halfLoop = loopLength / 2;
                 
                 if (p.x < -halfLoop) {
                     p.x += loopLength;
                 }

                 // Direct DOM update
                 const el = photoRefs.value[i];
                 if (el) {
                     el.style.transform = `translate3d(${p.x}px, ${p.y}px, ${p.z}px) rotateX(${p.rX}deg) rotateY(${p.rY}deg) rotateZ(${p.rZ}deg) scale(${p.scale})`;
                     el.style.width = `${p.width}px`;
                     el.style.height = `${p.height}px`;
                     el.style.transition = 'none';
                 }
             });
        }
        animationFrameId = requestAnimationFrame(loop);
    };
    loop();
};

const getPhotoStyle = (index: number) => {
    const p = positions.value[index];
    if (!p) return {};

    // In Stage 1, we want per-photo transition delays for "random fly-in" effect logic
    // But we used a single state update.
    // To achieve "0.05s interval start", we can use transition-delay in style.
    const delay = currentStage.value === 1 ? index * 0.05 : 0;

    // Duration
    let duration = '1.5s';
    if (currentStage.value === 1) duration = '2.5s';
    if (currentStage.value === 4) duration = '0s'; // No transition during scroll loop
    if (currentStage.value === 3 || currentStage.value === 4) {
        return {
            transform: `translate3d(${p.x}px, ${p.y}px, ${p.z}px) rotateX(${p.rX}deg) rotateY(${p.rY}deg) rotateZ(${p.rZ}deg) scale(${p.scale})`,
            width: p.width ? `${p.width}px` : undefined,
            height: p.height ? `${p.height}px` : undefined,
            opacity: p.opacity,
            transition: currentStage.value === 4 ? 'none' : `all ${duration} cubic-bezier(0.25, 0.46, 0.45, 0.94)`,
            transitionDelay: `${delay}s`,
        };
    } else {
        return {
            transform: `translate3d(${p.x}px, ${p.y}px, ${p.z}px) rotateX(${p.rX}deg) rotateY(${p.rY}deg) rotateZ(${p.rZ}deg) scale(${p.scale})`,
            opacity: p.opacity,
            transition: currentStage.value === 4 ? 'none' : `all ${duration} cubic-bezier(0.25, 0.46, 0.45, 0.94)`,
            transitionDelay: `${delay}s`,
        };
    }

};

// Interaction for Sphere
const isDragging = ref(false);
const lastMousePos = ref({ x: 0, y: 0 });
const sphereRotation = ref({ x: 0, y: 0 });

const handleMouseDown = (e: MouseEvent | TouchEvent) => {
    if (currentStage.value !== 2) return;
    isDragging.value = true;
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;
    const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY;
    lastMousePos.value = { x: clientX, y: clientY };
};

const handleMouseMove = (e: MouseEvent | TouchEvent) => {
    if (!isDragging.value || currentStage.value !== 2) return;
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;
    const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY;
    
    const deltaX = clientX - lastMousePos.value.x;
    const deltaY = clientY - lastMousePos.value.y;
    
    sphereRotation.value.y += deltaX * 0.5;
    sphereRotation.value.x -= deltaY * 0.5;
    
    lastMousePos.value = { x: clientX, y: clientY };
};

const handleMouseUp = () => {
    isDragging.value = false;
};

const getSceneStyle = computed(() => {
    if (currentStage.value === 2) {
        return {
            transform: `rotateX(${sphereRotation.value.x}deg) rotateY(${sphereRotation.value.y}deg)`,
            transition: isDragging.value ? 'none' : 'transform 1s ease-out'
        };
    }
    return {
        transform: 'none',
        transition: 'transform 1s ease-in-out'
    };
});

const togglePause = () => {
    if (currentStage.value === 4) {
        isPaused.value = !isPaused.value;
    }
};

const checkVisibilityAndAnimate = () => {
    if (!loading.value && !hasStartedAnimation.value && isVisible.value) {
        hasStartedAnimation.value = true;
        startAnimationSequence();
    }
};


onMounted(() => {
    fetchPhotos();
    window.addEventListener('mouseup', handleMouseUp);
    window.addEventListener('touchend', handleMouseUp);
});

onUnmounted(() => {
    cancelAnimationFrame(animationFrameId);
    window.removeEventListener('mouseup', handleMouseUp);
    window.removeEventListener('touchend', handleMouseUp);
});

</script>

<style scoped>
.perspective-container {
    perspective: 2000px;
}
.transform-style-3d {
    transform-style: preserve-3d;
}
.photo-card {
    /* Optimization */
    will-change: transform, opacity;
    /* backface-visibility: hidden; Removed to allow full sphere visibility */
}
</style>

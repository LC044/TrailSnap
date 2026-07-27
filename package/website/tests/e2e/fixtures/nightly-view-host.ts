import { createApp, defineComponent, h, onMounted, ref } from 'vue'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import 'element-plus/dist/index.css'
import '@/style.css'

import RegionDetailsPanel from '@/views/album/location/components/RegionDetailsPanel.vue'
import ScreenshotCleanupDialog from '@/views/settings/ScreenshotCleanupDialog.vue'
import type { AlbumImage } from '@/types/album'
import type { TimelineNode } from '@/types/location'

const fixture = new URLSearchParams(window.location.search).get('fixture') ?? 'region'
const pixel =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='

const photos: AlbumImage[] = [
  {
    id: 'region-photo-1',
    url: pixel,
    thumbnail: pixel,
    preview: pixel,
    srcset: '',
    timestamp: Date.parse('2026-04-05T10:00:00Z'),
    albumIds: [],
    filename: 'east-lake.png',
    file_type: 'image',
    size: 1024,
  },
]

const visits: TimelineNode[] = [
  {
    type: 'city',
    startDate: '2026-04-05',
    endDate: '2026-04-06',
    locationName: '\u6b66\u6c49\u5e02',
    level: 'city',
    photoCount: 8,
  },
]

const NightlyViewHost = defineComponent({
  name: 'NightlyViewHost',
  setup() {
    const visible = ref(fixture === 'screenshots' ? false : true)
    const events = ref<string[]>([])

    const record = (event: string) => {
      events.value = [...events.value, event]
    }

    onMounted(() => {
      if (fixture === 'screenshots') visible.value = true
    })

    return () => {
      let view

      if (fixture === 'region' || fixture === 'region-empty') {
        const empty = fixture === 'region-empty'
        view = h(RegionDetailsPanel, {
          level: empty ? 'city' : 'province',
          selectedRegion: empty ? '\u6b66\u6c49\u5e02' : '\u6e56\u5317\u7701',
          selectedRegionCount: empty ? 0 : 12,
          regionPhotos: empty ? [] : photos,
          regionTimeSpan: empty ? '' : '2024-2026',
          regionFirstVisit: empty ? '' : '2024-05-01',
          regionTags: empty ? [] : [{ name: '\u6c5f\u57ce', count: 4 }],
          regionSubLevel: empty ? 'district' : 'city',
          regionExploredCount: empty ? 0 : 3,
          regionTotalCount: empty ? 4 : 6,
          regionTopSubRegions: empty
            ? []
            : [
                { name: '\u6b66\u6c49\u5e02', count: 8 },
                { name: '\u9ec4\u77f3\u5e02', count: 4 },
              ],
          regionRecentVisits: empty ? [] : visits,
          onClearSelection: () => record('clear-selection'),
          onClickLocation: (name: string, level?: string) =>
            record(`click-location:${name}:${level ?? 'none'}`),
          onChangeLevel: (
            level: string,
            state: { parentRegion?: string },
          ) => record(`change-level:${level}:${state.parentRegion ?? 'none'}`),
        })
      } else if (fixture === 'screenshots') {
        view = h(ScreenshotCleanupDialog, {
          modelValue: visible.value,
          'onUpdate:modelValue': (value: boolean) => {
            visible.value = value
            record(`visible:${value}`)
          },
        })
      } else {
        view = h('p', { id: 'unknown-fixture' }, `Unknown fixture: ${fixture}`)
      }

      return h('main', { id: 'nightly-view-host' }, [
        view,
        h('pre', { id: 'event-log' }, events.value.join('\n')),
      ])
    }
  },
})

createApp(NightlyViewHost).use(createPinia()).use(ElementPlus).mount('#app')

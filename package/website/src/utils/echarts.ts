// src/utils/echarts.ts
//
// 集中按需注册 echarts：仅引入项目实际用到的图表类型、组件与渲染器，
// 避免整包 `import * as echarts from 'echarts'`（约 1MB）进打包。
//
// 业务文件统一写：
//   import { echarts } from '@/utils/echarts'
// 用法与原先 `import * as echarts from 'echarts'` 完全一致——
// echarts.init / echarts.graphic.LinearGradient / echarts.registerMap 均在 core 上可用。
//
// 新增图表类型或组件时，在下方 use([...]) 里补注册即可。
import * as echarts from 'echarts/core'

// —— 图表类型（series.type）——
import {
  LineChart,
  BarChart,
  PieChart,
  RadarChart,
  TreemapChart,
  MapChart,
  LinesChart,
  EffectScatterChart,
} from 'echarts/charts'

// —— 组件（option 顶层键）——
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  VisualMapComponent,
  DataZoomComponent,
  GeoComponent,
  ToolboxComponent,
  AxisPointerComponent,
  RadarComponent,
  DatasetComponent,
} from 'echarts/components'

// —— 渲染器 ——
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  // charts
  LineChart,
  BarChart,
  PieChart,
  RadarChart,
  TreemapChart,
  MapChart,
  LinesChart,
  EffectScatterChart,
  // components
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  VisualMapComponent,
  DataZoomComponent,
  GeoComponent,
  ToolboxComponent,
  AxisPointerComponent,
  RadarComponent,
  DatasetComponent,
  // renderer
  CanvasRenderer,
])

export { echarts }
export default echarts

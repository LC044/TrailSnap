import { ref, watch, computed, provide, inject, onMounted, onUnmounted, InjectionKey, ComputedRef, Ref } from 'vue';

// ----------------- 1. 定义核心类型接口（TS 核心）-----------------
/** 主题颜色配置类型 */
export interface ThemeColor {
  name: 'sky' | 'emerald' | 'violet' | 'rose' | 'amber'; // 限定主题名可选值
  label: string; // 主题显示名称
  primary: string; // 主色值（十六进制）
  secondary: string; // 辅助色值
  rgb: string; // 主色 RGB 值（用于透明叠加等场景）
}

/** 主题模式类型（限定可选值） */
export type ThemeMode = 'light' | 'auto' | 'dark';

/** 提供/注入的主题对象类型（汇总所有状态和方法） */
export interface ThemeProvide {
  isDarkMode: ComputedRef<boolean>;
  currentMode: Ref<ThemeMode>;
  currentTheme: Ref<ThemeColor>;
  themeStyle: ComputedRef<Record<string, string>>;
  themeColors: ThemeColor[];
  setMode: (mode: ThemeMode) => void;
  setTheme: (themeObj: ThemeColor) => void;
}

// ----------------- 2. 主题配置（保持原数据不变，添加类型约束）-----------------
export const themeColors: ThemeColor[] = [
  { name: 'sky', label: '天空蓝', primary: '#1E88E5', secondary: '#64B5F6', rgb: '30, 136, 229' },
  { name: 'emerald', label: '森系绿', primary: '#10B981', secondary: '#34D399', rgb: '16, 185, 129' },
  { name: 'violet', label: '梦幻紫', primary: '#8B5CF6', secondary: '#A78BFA', rgb: '139, 92, 246' },
  { name: 'rose', label: '落日红', primary: '#F43F5E', secondary: '#FB7185', rgb: '244, 63, 94' },
  { name: 'amber', label: '复古橘', primary: '#F59E0B', secondary: '#FBBF24', rgb: '245, 158, 11' },
];

// ----------------- 3. 类型化 Injection Key（避免注入类型丢失）-----------------
/** 主题注入的唯一 Key（TS 泛型指定注入类型为 ThemeProvide） */
const ThemeInjectionKey: InjectionKey<ThemeProvide> = Symbol('theme');

// ----------------- 4. 核心逻辑（添加类型注解，逻辑不变）-----------------
export function useTheme(): ThemeProvide {
  // 状态初始化（从 localStorage 读取或默认值，添加类型注解）
  const savedMode = localStorage.getItem('theme-mode') as ThemeMode | null;
  const currentMode = ref<ThemeMode>(savedMode || 'auto'); // 初始化为 ThemeMode 类型

  const savedColor = localStorage.getItem('theme-color');
  const initialTheme = themeColors.find(t => t.name === savedColor) || themeColors[0];
  const currentTheme = ref<ThemeColor>(initialTheme); // 初始化为 ThemeColor 类型

  // 用于触发系统主题变化时的响应式更新
  const systemPreferenceChange = ref(0);

  // 计算是否为深色模式（返回值类型：boolean）
  const isDarkMode = computed<boolean>(() => {
    systemPreferenceChange.value; // 依赖追踪，确保系统主题变化时重新计算
    if (currentMode.value === 'dark') return true;
    if (currentMode.value === 'light') return false;
    // 'auto' 模式：监听系统偏好（TS 自动识别 matchMedia 返回类型）
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  // 计算 CSS 变量（返回值类型：{ [key: string]: string }）
  const themeStyle = computed<Record<string, string>>(() => {
    return {
      '--theme-primary': currentTheme.value.primary,
      '--theme-rgb': currentTheme.value.rgb,
      '--text-color': isDarkMode.value ? '#ffffff' : '#1e293b',
    };
  });

  // 设置主题模式（参数类型约束为 ThemeMode，避免传错值）
  const setMode = (mode: ThemeMode): void => {
    currentMode.value = mode;
    localStorage.setItem('theme-mode', mode);
    systemPreferenceChange.value++; // 强制更新 isDarkMode
    console.log(`🌗 主题模式已切换为：${mode}`);
  };

  // 设置主题颜色（参数类型约束为 ThemeColor）
  const setTheme = (themeObj: ThemeColor): void => {
    currentTheme.value = themeObj;
    localStorage.setItem('theme-color', themeObj.name);
  };

  // 监听系统主题变化（TS 注解事件参数类型）
  onMounted(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    // 事件回调参数类型：MediaQueryListEvent
    const listener = (e: MediaQueryListEvent): void => {
      if (currentMode.value === 'auto') {
        systemPreferenceChange.value++;
      }
    };

    mediaQuery.addEventListener('change', listener);
    onUnmounted(() => {
      mediaQuery.removeEventListener('change', listener);
    });
  });

  // 实时同步 dark class 到 HTML 根元素
  watch(
    isDarkMode,
    (newVal) => {
      const root = document.documentElement;
      root.classList.toggle('dark', newVal);
    },
    { immediate: true }
  );

  // 同步主题 CSS 变量到 <html> 根元素。
  // el-dropdown / el-popover / el-select 等弹层默认 teleport 到 <body>，
  // 脱离了 MainLayout（--theme-primary 仅在其根节点上声明）的作用域，
  // 导致弹层内 var(--theme-primary) 失效、回退成 Element Plus 默认灰色。
  // 写到 document.documentElement 后全局可用。
  watch(
    themeStyle,
    (style) => {
      const root = document.documentElement;
      Object.entries(style).forEach(([k, v]) => root.style.setProperty(k, v));
    },
    { immediate: true }
  );

  // 返回所有状态和方法（严格匹配 ThemeProvide 类型）
  return {
    isDarkMode,
    currentMode,
    currentTheme,
    themeStyle,
    themeColors,
    setMode,
    setTheme,
  };
}

// ----------------- 5. 类型化 Provide/Inject（确保注入类型安全）-----------------
/** 根组件提供主题（返回类型为 ThemeProvide） */
export function provideTheme(): ThemeProvide {
  const theme = useTheme();
  provide(ThemeInjectionKey, theme); // 注入时绑定类型
  return theme;
}

/** 子组件注入主题（自动推断返回类型为 ThemeProvide） */
export function injectTheme(): ThemeProvide {
  const theme = inject(ThemeInjectionKey);
  if (!theme) {
    throw new Error('❌ 主题未提供！请在根组件调用 provideTheme()');
  }
  return theme;
}
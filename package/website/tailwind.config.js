/** @type {import('tailwindcss').Config} */
const { addDynamicIconSelectors } = require('@iconify/tailwind')
const defaultTheme = require('tailwindcss/defaultTheme')

// Scale spacing without changing width/height utilities or control hit areas.
const scaleRemValues = (values) => Object.fromEntries(
  Object.entries(values).map(([key, value]) => [key,
    typeof value === 'string' && value.endsWith('rem')
      ? `calc(var(--ts-spacing-unit, 1rem) * ${parseFloat(value)})`
      : value,
  ]),
)
const scaledSpacing = scaleRemValues(defaultTheme.spacing)

// Existing gray/slate/neutral utilities share one neutral scale during migration.
const neutral = {
  50: '#f5f6f8', 100: '#eef0f3', 200: '#dfe3e9', 300: '#c8cfd9',
  400: '#8d98a8', 500: '#647184', 600: '#4d596b', 700: '#303947',
  800: '#1b2028', 900: '#101318', 950: '#090b0f',
}

// 无 /N 透明度修饰符时，Tailwind 传入 'var(--tw-bg-opacity, 1)' 这类占位串，
// Number() 后为 NaN；此时直接用档位固有的强度值，有修饰符时才与数值相乘。
// 曾因把占位串当数值运算输出 rgba(var(--theme-rgb), NaN)，整条声明被浏览器
// 丢弃，@apply 该色的元素（如 AI 助手用户气泡）背景完全透明。
const themedColor = (strength = 1) => ({ opacityValue }) => {
  const modifier = Number(opacityValue)
  const opacity = Number.isFinite(modifier) ? modifier * strength : strength
  return `rgba(var(--theme-rgb), ${opacity})`
}

export default {
  darkMode: 'class',
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ['var(--ts-font-sans)'] },
      padding: scaledSpacing,
      margin: scaledSpacing,
      gap: scaledSpacing,
      space: scaledSpacing,
      borderRadius: scaleRemValues(defaultTheme.borderRadius),
      borderWidth: Object.fromEntries(Object.entries(defaultTheme.borderWidth).map(([key, value]) => [
        key, parseFloat(value) ? `calc(var(--ts-border-unit, 1px) * ${parseFloat(value)})` : value,
      ])),
      fontSize: {
        sm: ['var(--ts-font-sm, 0.875rem)', { lineHeight: '1.25rem' }],
        xs: ['var(--ts-font-xs, 0.75rem)', { lineHeight: '1rem' }],
      },
      colors: {
        gray: neutral, slate: neutral, neutral,
        // Runtime theme palette. Lower steps are translucent surfaces; higher
        // steps keep the selected theme hue for text, borders and controls.
        primary: {
          50: themedColor(0.08),
          100: themedColor(0.12),
          200: themedColor(0.22),
          300: themedColor(0.45),
          400: themedColor(0.75),
          500: themedColor(1),
          600: themedColor(1),
          700: themedColor(1),
          800: themedColor(0.82),
          900: themedColor(0.68),
        },
        // Annual Report Colors
        'primary-amber': '#F97316',
        'bg-light': '#FAF6F0',
        'bg-dark': '#334155',
        'bg-top': '#FAF6F0', // Light mode gradient top
        'bg-bottom': '#FEE2D0', // Light mode gradient bottom
        
        // Existing Colors
        'light-bg': '#FAFAFA',
        'light-bg1': '#f8fafc',
        'light-text1': '#333333',
        'light-text2': '#2C3E50',
        'light-text3': '#34495E',
        'light-beige': '#FAFAFA',
        'light-gray': '#F5F5F5',
        'light-warm-white': '#FDFDFD',
        'dark-gray-blue': '#282C34',
        'dark-navy': '#1E293B',
        'dark-warm-gray': '#333333',
        'light-dark-gray': '#333333',
        'light-charcoal': '#2C3E50',
        'light-blue-gray': '#34495E',
        'dark-text-warm-gray': '#E0E0E0',
        'dark-blue-gray': '#CBD5E1',
        'dark-gray-yellow': '#E6E2AF',
        'accent-fresh-blue': '#4FC3F7',
        'accent-fresh-mint': '#4DB6AC',
        'accent-fresh-purple': '#9575CD',
        'accent-natural-brown': '#8D6E63',
        'accent-natural-gray-blue': '#78909C',
        'accent-natural-light-cyan': '#5F9EA0',
      },
      // Custom Utilities
      utilities: {
        '.page-item': {
          '@apply snap-start h-screen w-full flex flex-col justify-center items-center p-6 box-border': {},
        }
      }
    },
  },
  plugins: [addDynamicIconSelectors()],
}

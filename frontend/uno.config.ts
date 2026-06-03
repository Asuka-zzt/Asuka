import { defineConfig, presetAttributify, presetUno } from 'unocss'

// 参考 AIRI uno.config.ts：原子化工具类 + attributify 写法。
// 主色对齐 AIRI 的 presetChromatic baseHue 220.44（azure/sky 蓝青），非紫色。
export default defineConfig({
  presets: [presetUno(), presetAttributify()],
  theme: {
    colors: {
      primary: {
        DEFAULT: '#1aa9d2',
        400: '#5cc4e3',
        500: '#1aa9d2',
        600: '#0090bc',
      },
    },
  },
})

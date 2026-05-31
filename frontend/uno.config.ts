import { defineConfig, presetAttributify, presetUno } from 'unocss'

// 参考 AIRI uno.config.ts，精简：原子化工具类 + attributify 写法。
export default defineConfig({
  presets: [presetUno(), presetAttributify()],
  theme: {
    colors: {
      primary: {
        DEFAULT: '#7c6cf0',
        400: '#9b8ef5',
        500: '#7c6cf0',
        600: '#6a59e0',
      },
    },
  },
})

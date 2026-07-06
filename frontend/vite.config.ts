import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import AutoImport from "unplugin-auto-import/vite";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";

export default defineConfig({
  plugins: [
    vue(),
    // 按需自动引入 element-plus 的 API（如 ElMessage/ElMessageBox）及其样式
    AutoImport({
      resolvers: [ElementPlusResolver()],
      dts: "src/auto-imports.d.ts",
    }),
    // 按需自动引入模板中用到的 element-plus 组件及其样式
    Components({
      resolvers: [ElementPlusResolver()],
      dts: "src/components.d.ts",
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  esbuild: {
    drop: ["console", "debugger"],
  },
  build: {
    target: "es2019",
    cssCodeSplit: true,
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      // 过滤第三方库（@vueuse/core）无法被 Rollup 解析的 #__PURE__ 注释警告，属上游产物问题，不影响功能
      onwarn(warning, warn) {
        if (
          warning.code === "INVALID_ANNOTATION" &&
          warning.message.includes("#__PURE__")
        ) {
          return;
        }
        warn(warning);
      },
      output: {
        // 将大依赖拆成独立 chunk，利于浏览器长期缓存
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("element-plus") || id.includes("@element-plus")) {
              return "element-plus";
            }
            if (id.includes("vue") || id.includes("@vue")) {
              return "vue";
            }
            return "vendor";
          }
        },
      },
    },
  },
});

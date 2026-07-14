<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuth } from "./composables/useAuth";
import AiAssistant from "./components/AiAssistant.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuth();

const activeMenu = computed(() => {
  if (route.path.startsWith("/admin/products")) return "/admin/products";
  if (route.path.startsWith("/about")) return "";
  return route.path;
});

function handleLogout() {
  auth.logout();
  router.push({ name: "home" });
}
</script>

<template>
  <div class="layout">
    <header class="navbar">
      <div class="navbar-inner">
        <router-link to="/" class="brand">
          <span class="brand-icon">🛒</span>
          <span class="brand-text">智能商城管理系统</span>
        </router-link>

        <el-menu
          mode="horizontal"
          :default-active="activeMenu"
          :ellipsis="false"
          router
          class="nav-menu"
        >
          <el-menu-item index="/">首页</el-menu-item>
          <el-menu-item v-if="auth.isLoggedIn.value" index="/admin/products">商品管理</el-menu-item>
        </el-menu>

        <div class="nav-actions">
          <template v-if="auth.isLoggedIn.value">
            <span class="username">你好，{{ auth.user.value?.username }}</span>
            <el-button type="danger" plain size="small" @click="handleLogout">退出</el-button>
          </template>
          <template v-else>
            <el-button type="primary" plain size="small" @click="router.push('/login')">登录</el-button>
            <el-button type="primary" size="small" @click="router.push('/register')">注册</el-button>
          </template>
          <el-button text class="about-link" @click="router.push('/about')">
            项目介绍
          </el-button>
        </div>
      </div>
    </header>

    <main class="main">
      <router-view />
    </main>

    <footer class="footer">
      <span>© 2026 智能商城管理系统</span>
    </footer>

    <AiAssistant />
  </div>
</template>

<style>
body {
  margin: 0;
  background: #f5f7fa;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial,
    "PingFang SC", "Microsoft YaHei", sans-serif;
}

.layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.navbar {
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  position: sticky;
  top: 0;
  z-index: 100;
}

.navbar-inner {
  width: 100%;
  margin: 0;
  padding: 0 24px;
  display: flex;
  align-items: center;
  gap: 24px;
  height: 60px;
  box-sizing: border-box;
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: #303133;
  flex-shrink: 0;
}

.brand-icon {
  font-size: 24px;
}

.brand-text {
  font-size: 20px;
  font-weight: 700;
  color: #409eff;
}

.nav-menu {
  flex: 1;
  border-bottom: none !important;
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.about-link {
  color: #606266;
  font-size: 14px;
  padding: 4px 8px;
  margin-left: 4px;
}

.about-link:hover {
  color: #409eff;
}

.username {
  font-size: 14px;
  color: #606266;
}

.main {
  flex: 1;
}

.footer {
  text-align: center;
  padding: 20px;
  color: #909399;
  font-size: 13px;
  background: #fff;
  border-top: 1px solid #ebeef5;
}
</style>

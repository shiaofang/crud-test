<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Search } from "@element-plus/icons-vue";
import { hotProductApi } from "../api";
import type { HotProduct } from "../types";

const loading = ref(false);
const products = ref<HotProduct[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(12);
const keyword = ref("");

async function fetchData() {
  loading.value = true;
  try {
    const res = await hotProductApi.list({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    });
    products.value = res.items;
    total.value = res.total;
  } catch {
    ElMessage.error("加载商品失败，请检查后端服务");
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  fetchData();
}

onMounted(fetchData);
</script>

<template>
  <div class="home">
    <section class="hero">
      <div class="hero-content">
        <h1>欢迎来到悦购商城</h1>
        <p>精选好物，品质生活 · 登录后可管理商品</p>
        <el-input
          v-model="keyword"
          placeholder="搜索你想要的商品..."
          size="large"
          clearable
          class="hero-search"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
          <template #append>
            <el-button type="primary" @click="handleSearch">搜索</el-button>
          </template>
        </el-input>
      </div>
    </section>

    <section class="products-section">
      <div class="section-header">
        <h2>热门商品</h2>
        <span class="count">共 {{ total }} 件</span>
      </div>

      <div v-loading="loading" class="product-grid">
        <el-card
          v-for="item in products"
          :key="item.id"
          shadow="hover"
          class="product-card"
        >
          <div class="product-image">
            <span class="product-emoji">📦</span>
          </div>
          <div class="product-info">
            <h3 class="product-name">{{ item.name }}</h3>
            <p class="product-desc">{{ item.description || "暂无描述" }}</p>
            <div class="product-footer">
              <span class="product-price">￥{{ Number(item.price).toFixed(2) }}</span>
              <el-tag :type="item.stock > 0 ? 'success' : 'info'" size="small">
                {{ item.stock > 0 ? `库存 ${item.stock}` : "缺货" }}
              </el-tag>
            </div>
          </div>
        </el-card>
      </div>

      <el-empty v-if="!loading && products.length === 0" description="暂无商品" />

      <div v-if="total > pageSize" class="pagination">
        <el-pagination
          background
          layout="prev, pager, next"
          :total="total"
          :current-page="page"
          :page-size="pageSize"
          @current-change="(p: number) => { page = p; fetchData(); }"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.home {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px 40px;
}

.hero {
  background: linear-gradient(135deg, #409eff 0%, #66b1ff 50%, #a0cfff 100%);
  border-radius: 12px;
  padding: 48px 40px;
  margin: 24px 0;
  color: #fff;
}

.hero-content h1 {
  margin: 0 0 8px;
  font-size: 32px;
  font-weight: 700;
}

.hero-content p {
  margin: 0 0 24px;
  opacity: 0.9;
  font-size: 16px;
}

.hero-search {
  max-width: 480px;
}

.products-section {
  margin-top: 8px;
}

.section-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 20px;
}

.section-header h2 {
  margin: 0;
  font-size: 22px;
  color: #303133;
}

.count {
  color: #909399;
  font-size: 14px;
}

.product-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px;
  min-height: 120px;
}

.product-card {
  transition: transform 0.2s;
}

.product-card:hover {
  transform: translateY(-4px);
}

.product-image {
  height: 140px;
  background: linear-gradient(135deg, #f0f9ff, #e8f4fd);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.product-emoji {
  font-size: 48px;
}

.product-name {
  margin: 0 0 6px;
  font-size: 16px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-desc {
  margin: 0 0 12px;
  font-size: 13px;
  color: #909399;
  height: 36px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.product-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.product-price {
  font-size: 20px;
  font-weight: 700;
  color: #f56c6c;
}

.pagination {
  display: flex;
  justify-content: center;
  margin-top: 32px;
}
</style>

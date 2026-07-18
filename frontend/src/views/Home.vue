<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

interface ActivityEvent {
  type?: string;
  action?: string;
  source?: "admin" | "ai";
  message?: string;
  product_id?: number | null;
  product_name?: string;
  actor?: string | null;
  ts?: string;
}

const items = ref<ActivityEvent[]>([]);
const connected = ref(false);
const errorText = ref("");

let source: EventSource | null = null;
const MAX_ITEMS = 40;

function formatTime(ts?: string) {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("zh-CN", { hour12: false });
}

function sourceLabel(sourceType?: string) {
  if (sourceType === "ai") return "AI";
  if (sourceType === "admin") return "管理";
  return "";
}

function connect() {
  errorText.value = "";
  source = new EventSource("/api/activities/stream");

  source.onopen = () => {
    connected.value = true;
  };

  source.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data) as ActivityEvent;
      if (data.type === "ping" || data.type === "connected") return;
      if (!data.message) return;
      items.value = [data, ...items.value].slice(0, MAX_ITEMS);
    } catch {
      // ignore malformed
    }
  };

  source.onerror = () => {
    connected.value = false;
    errorText.value = "动态流连接中断，正在重试…";
  };
}

onMounted(connect);

onUnmounted(() => {
  source?.close();
  source = null;
});
</script>

<template>
  <div class="home">
    <section class="hero">
      <div class="hero-content">
        <h1>智能商城管理系统</h1>
        <p>商品与用户一站管理 · 登录后可使用智能助手</p>
      </div>
    </section>

    <section class="feed">
      <div class="feed-head">
        <h2>实时动态</h2>
        <span class="status" :class="{ on: connected }">
          {{ connected ? "已连接" : "连接中…" }}
        </span>
      </div>
      <p class="feed-desc">基于 Kafka 推送商品创建 / 更新 / 删除（含 AI 助手操作）</p>
      <p v-if="errorText" class="feed-error">{{ errorText }}</p>

      <ul v-if="items.length" class="feed-list">
        <li v-for="(item, idx) in items" :key="`${item.ts}-${idx}`" class="feed-item">
          <span class="time">{{ formatTime(item.ts) }}</span>
          <span v-if="sourceLabel(item.source)" class="tag" :class="item.source">
            {{ sourceLabel(item.source) }}
          </span>
          <span class="msg">{{ item.message }}</span>
        </li>
      </ul>
      <div v-else class="feed-empty">
        暂无动态。去「商品管理」增删改，或让 AI 助手改商品，这里会实时出现。
      </div>
    </section>
  </div>
</template>

<style scoped>
.home {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 0 24px 40px;
  box-sizing: border-box;
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
  margin: 0;
  opacity: 0.9;
  font-size: 16px;
}

.feed {
  background: #fff;
  border-radius: 12px;
  padding: 24px 28px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.feed-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.feed-head h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.status {
  font-size: 12px;
  color: #909399;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f0f2f5;
}

.status.on {
  color: #67c23a;
  background: #f0f9eb;
}

.feed-desc {
  margin: 8px 0 0;
  font-size: 13px;
  color: #909399;
}

.feed-error {
  margin: 8px 0 0;
  font-size: 13px;
  color: #e6a23c;
}

.feed-list {
  list-style: none;
  margin: 16px 0 0;
  padding: 0;
  max-height: 420px;
  overflow-y: auto;
}

.feed-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 0;
  border-bottom: 1px solid #ebeef5;
  font-size: 14px;
  color: #303133;
  animation: fadeIn 0.25s ease;
}

.feed-item:last-child {
  border-bottom: none;
}

.time {
  flex: 0 0 auto;
  color: #909399;
  font-variant-numeric: tabular-nums;
  font-size: 13px;
}

.tag {
  flex: 0 0 auto;
  font-size: 12px;
  line-height: 1;
  padding: 3px 6px;
  border-radius: 4px;
  color: #fff;
}

.tag.admin {
  background: #409eff;
}

.tag.ai {
  background: #9b59b6;
}

.msg {
  flex: 1;
  min-width: 0;
  line-height: 1.5;
}

.feed-empty {
  margin-top: 20px;
  padding: 28px 16px;
  text-align: center;
  color: #909399;
  font-size: 14px;
  background: #fafafa;
  border-radius: 8px;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>

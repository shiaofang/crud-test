<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { ChatDotRound, Close, Promotion } from "@element-plus/icons-vue";
import { chatApi } from "../api";
import type { ChatMessage } from "../types";
import { notifyDataRefresh } from "../composables/useDataRefresh";

const PANEL_MIN_W = 360;
const PANEL_MIN_H = 420;
const PANEL_DEFAULT_W = 520;
const PANEL_DEFAULT_H = 680;

const open = ref(false);
const loading = ref(false);
const input = ref("");
const panelW = ref(PANEL_DEFAULT_W);
const panelH = ref(PANEL_DEFAULT_H);
const resizing = ref(false);
const messages = ref<ChatMessage[]>([
  {
    role: "assistant",
    content:
      "您好，我是智能商城助手，可以帮你查询和管理商品、用户数据。有问题可以随时问我。"
  },
]);
const listRef = ref<HTMLElement | null>(null);
let abortCtrl: AbortController | null = null;
let resizeStartX = 0;
let resizeStartY = 0;
let resizeStartW = 0;
let resizeStartH = 0;

const panelStyle = computed(() => ({
  width: `${panelW.value}px`,
  height: `${panelH.value}px`,
  maxWidth: "calc(100vw - 32px)",
  maxHeight: "calc(100vh - 100px)",
}));

function clampPanelSize(w: number, h: number) {
  const maxW = Math.max(PANEL_MIN_W, window.innerWidth - 32);
  const maxH = Math.max(PANEL_MIN_H, window.innerHeight - 100);
  panelW.value = Math.min(maxW, Math.max(PANEL_MIN_W, w));
  panelH.value = Math.min(maxH, Math.max(PANEL_MIN_H, h));
}

function onResizeMove(e: PointerEvent) {
  if (!resizing.value) return;
  // 面板贴右下角：向左拖变宽，向上拖变高
  const nextW = resizeStartW + (resizeStartX - e.clientX);
  const nextH = resizeStartH + (resizeStartY - e.clientY);
  clampPanelSize(nextW, nextH);
}

function stopResize() {
  if (!resizing.value) return;
  resizing.value = false;
  window.removeEventListener("pointermove", onResizeMove);
  window.removeEventListener("pointerup", stopResize);
  window.removeEventListener("pointercancel", stopResize);
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
}

function startResize(e: PointerEvent) {
  e.preventDefault();
  resizing.value = true;
  resizeStartX = e.clientX;
  resizeStartY = e.clientY;
  resizeStartW = panelW.value;
  resizeStartH = panelH.value;
  document.body.style.cursor = "nwse-resize";
  document.body.style.userSelect = "none";
  window.addEventListener("pointermove", onResizeMove);
  window.addEventListener("pointerup", stopResize);
  window.addEventListener("pointercancel", stopResize);
}

onBeforeUnmount(() => {
  stopResize();
});

function cancelRequest() {
  abortCtrl?.abort();
  abortCtrl = null;
  loading.value = false;
}

watch(open, async (val) => {
  if (val) {
    await nextTick();
    scrollToBottom();
  } else {
    cancelRequest();
  }
});

function scrollToBottom() {
  const el = listRef.value;
  if (el) el.scrollTop = el.scrollHeight;
}

function isAbortError(err: unknown) {
  return err instanceof DOMException
    ? err.name === "AbortError"
    : err instanceof Error && err.name === "AbortError";
}

async function send() {
  const text = input.value.trim();
  if (!text) return;

  // 上一轮还在跑时允许打断，避免后台继续批量写库
  if (loading.value) {
    cancelRequest();
  }

  const history = messages.value
    .filter((m, i) => !(i === 0 && m.role === "assistant"))
    .filter((m) => m.content.trim())
    .map(({ role, content }) => ({ role, content }));

  messages.value.push({ role: "user", content: text });
  input.value = "";
  loading.value = true;

  messages.value.push({ role: "assistant", content: "", steps: [] });
  const assistantIndex = messages.value.length - 1;
  await nextTick();
  scrollToBottom();

  abortCtrl?.abort();
  abortCtrl = new AbortController();
  const { signal } = abortCtrl;

  try {
    await chatApi.stream(
      { message: text, history },
      {
        onDelta: async (delta) => {
          if (signal.aborted) return;
          messages.value[assistantIndex].content += delta;
          await nextTick();
          scrollToBottom();
        },
        onClearDelta: () => {
          if (signal.aborted) return;
          messages.value[assistantIndex].content = "";
        },
        onStatus: async (status) => {
          if (signal.aborted) return;
          const steps = [...(messages.value[assistantIndex].steps ?? [])];
          steps.push(status);
          messages.value[assistantIndex].steps = steps;
          await nextTick();
          scrollToBottom();
        },
        onStatusDelta: async (delta) => {
          if (signal.aborted) return;
          const steps = [...(messages.value[assistantIndex].steps ?? [])];
          if (!steps.length) {
            steps.push(delta);
          } else {
            steps[steps.length - 1] = (steps[steps.length - 1] || "") + delta;
          }
          messages.value[assistantIndex].steps = steps;
          await nextTick();
          scrollToBottom();
        },
        onDone: (refresh) => {
          if (!signal.aborted) notifyDataRefresh(refresh);
        },
      },
      signal,
    );
    if (signal.aborted) return;
    if (!messages.value[assistantIndex].content.trim()) {
      messages.value[assistantIndex].content = "助手没有返回内容，请稍后再试";
    }
  } catch (err: unknown) {
    if (isAbortError(err)) return;
    const detail = err instanceof Error ? err.message : "助手暂时无法回复，请稍后再试";
    const current = messages.value[assistantIndex].content;
    messages.value[assistantIndex].content = current || String(detail);
  } finally {
    if (abortCtrl?.signal === signal) {
      abortCtrl = null;
    }
    loading.value = false;
    await nextTick();
    scrollToBottom();
  }
}

function onKeydown(e: Event | KeyboardEvent) {
  if (!(e instanceof KeyboardEvent)) return;
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
}
</script>

<template>
  <div class="ai-assistant">
    <Transition name="panel">
      <div v-if="open" class="chat-panel" :class="{ resizing }" :style="panelStyle" role="dialog" aria-label="智能助手">
        <div class="resize-handle" title="拖拽调整大小" aria-label="拖拽调整大小" @pointerdown="startResize" />
        <header class="chat-header">
          <div class="chat-title">
            <el-icon :size="18">
              <ChatDotRound />
            </el-icon>
            <span>智能商城助手</span>
          </div>
          <button type="button" class="icon-btn" aria-label="关闭" @click="open = false">
            <el-icon :size="18">
              <Close />
            </el-icon>
          </button>
        </header>

        <div ref="listRef" class="chat-messages">
          <div v-for="(msg, idx) in messages" :key="idx" class="msg" :class="msg.role">
            <div class="msg-body">
              <div v-if="msg.role === 'assistant' && msg.steps?.length" class="steps">
                <div class="steps-title">思考过程</div>
                <div v-for="(step, sIdx) in msg.steps" :key="sIdx" class="step">
                  {{ step }}
                </div>
              </div>
              <div v-if="msg.content || (loading && idx === messages.length - 1 && !msg.steps?.length)" class="bubble"
                :class="{ typing: loading && idx === messages.length - 1 && !msg.content }">
                {{
                  msg.content ||
                  (loading && idx === messages.length - 1 ? "正在思考…" : "")
                }}
              </div>
            </div>
          </div>
        </div>

        <footer class="chat-input">
          <el-input v-model="input" type="textarea" :rows="2" resize="none"
            :placeholder="loading ? '思考中…可输入新问题打断' : '问本系统相关问题，Enter 发送'" @keydown="onKeydown" />
          <el-button type="primary" :icon="Promotion" :loading="loading" :disabled="!input.trim()" circle
            @click="send" />
        </footer>
      </div>
    </Transition>

    <button type="button" class="fab" :class="{ active: open }" :aria-label="open ? '关闭智能助手' : '打开智能助手'"
      @click="open = !open">
      <el-icon :size="28">
        <Close v-if="open" />
        <ChatDotRound v-else />
      </el-icon>
    </button>
  </div>
</template>

<style scoped>
.ai-assistant {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
}

.fab {
  width: 56px;
  height: 56px;
  border: none;
  border-radius: 50%;
  background: linear-gradient(145deg, #409eff, #2b7fd4);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 20px rgba(64, 158, 255, 0.35);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.fab:hover {
  transform: translateY(-2px) scale(1.04);
  box-shadow: 0 10px 24px rgba(64, 158, 255, 0.45);
}

.fab.active {
  background: #606266;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
}

.chat-panel {
  position: relative;
  width: 520px;
  height: 680px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.14);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #ebeef5;
}

.chat-panel.resizing {
  transition: none;
}

.resize-handle {
  position: absolute;
  top: 0;
  left: 0;
  width: 18px;
  height: 18px;
  z-index: 2;
  cursor: nwse-resize;
  touch-action: none;
}

.resize-handle::before {
  content: "";
  position: absolute;
  top: 5px;
  left: 5px;
  width: 8px;
  height: 8px;
  border-top: 2px solid rgba(255, 255, 255, 0.85);
  border-left: 2px solid rgba(255, 255, 255, 0.85);
  border-radius: 1px;
  pointer-events: none;
}

.resize-handle:hover::before,
.chat-panel.resizing .resize-handle::before {
  border-color: #fff;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: linear-gradient(135deg, #409eff, #337ecc);
  color: #fff;
}

.chat-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 15px;
}

.icon-btn {
  border: none;
  background: transparent;
  color: #fff;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  display: flex;
}

.icon-btn:hover {
  background: rgba(255, 255, 255, 0.15);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: #f7f9fc;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.msg {
  display: flex;
}

.msg.user {
  justify-content: flex-end;
}

.msg.assistant {
  justify-content: flex-start;
}

.msg-body {
  max-width: 85%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.msg.user .msg-body {
  align-items: flex-end;
}

.steps {
  padding: 8px 10px;
  border-radius: 10px;
  background: #eef3f9;
  border: 1px dashed #c0c4cc;
  font-size: 12px;
  line-height: 1.45;
  color: #606266;
}

.steps-title {
  font-size: 11px;
  font-weight: 600;
  color: #909399;
  margin-bottom: 4px;
}

.step {
  padding: 2px 0;
  word-break: break-word;
  white-space: pre-wrap;
}

.step+.step {
  border-top: 1px solid rgba(192, 196, 204, 0.45);
  margin-top: 2px;
  padding-top: 4px;
}

.bubble {
  padding: 10px 12px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.msg.user .bubble {
  background: #409eff;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.msg.assistant .bubble {
  background: #fff;
  color: #303133;
  border: 1px solid #e4e7ed;
  border-bottom-left-radius: 4px;
}

.typing {
  color: #909399;
  font-style: italic;
}

.chat-input {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #ebeef5;
  background: #fff;
}

.chat-input :deep(.el-textarea__inner) {
  box-shadow: none;
  border: 1px solid #dcdfe6;
  border-radius: 10px;
}

.panel-enter-active,
.panel-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.panel-enter-from,
.panel-leave-to {
  opacity: 0;
  transform: translateY(12px) scale(0.96);
}
</style>

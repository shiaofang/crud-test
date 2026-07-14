import { onMounted, onUnmounted } from "vue";

export type DataResource = "products" | "users";

type RefreshListener = (resources: DataResource[]) => void;

const listeners = new Set<RefreshListener>();

/** 通知各页面：助手已成功改库，需要重新拉取数据。 */
export function notifyDataRefresh(resources: string[]) {
  const typed = resources.filter(
    (r): r is DataResource => r === "products" || r === "users",
  );
  if (!typed.length) return;
  for (const listener of listeners) {
    listener(typed);
  }
}

/** 在页面组件中订阅数据刷新（组件卸载时自动取消）。 */
export function onDataRefresh(listener: RefreshListener) {
  onMounted(() => listeners.add(listener));
  onUnmounted(() => listeners.delete(listener));
}

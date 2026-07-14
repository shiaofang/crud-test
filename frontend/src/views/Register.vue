<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { User, Lock, Message } from "@element-plus/icons-vue";
import type { FormInstance, FormRules } from "element-plus";
import { useAuth } from "../composables/useAuth";

const router = useRouter();
const auth = useAuth();

const formRef = ref<FormInstance>();
const loading = ref(false);

const form = reactive({
  username: "",
  email: "",
  password: "",
  confirmPassword: "",
});

const rules: FormRules = {
  username: [
    { required: true, message: "请输入用户名", trigger: "blur" },
    { min: 3, max: 50, message: "用户名长度 3-50 个字符", trigger: "blur" },
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 6, message: "密码至少 6 位", trigger: "blur" },
  ],
  confirmPassword: [
    { required: true, message: "请确认密码", trigger: "blur" },
    {
      validator: (_rule, value, callback) => {
        if (value !== form.password) callback(new Error("两次密码不一致"));
        else callback();
      },
      trigger: "blur",
    },
  ],
};

async function submit() {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    try {
      await auth.register(form.username, form.password, form.email || undefined);
      ElMessage.success("注册成功，已自动登录");
      router.push("/");
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "注册失败";
      ElMessage.error(typeof msg === "string" ? msg : "注册失败");
    } finally {
      loading.value = false;
    }
  });
}
</script>

<template>
  <div class="auth-page">
    <el-card shadow="never" class="auth-card">
      <h2 class="title">注册账号</h2>
      <p class="subtitle">注册账号，管理商品与用户</p>

      <el-form ref="formRef" :model="form" :rules="rules" label-width="0" size="large">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名（3-50 字符）">
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item prop="email">
          <el-input v-model="form.email" placeholder="邮箱（选填）">
            <template #prefix><el-icon><Message /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码（至少 6 位）"
            show-password
          >
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            placeholder="确认密码"
            show-password
            @keyup.enter="submit"
          >
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" class="submit-btn" @click="submit">
            注册
          </el-button>
        </el-form-item>
      </el-form>

      <div class="footer-link">
        已有账号？
        <router-link to="/login">立即登录</router-link>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.auth-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 140px);
  padding: 40px 20px;
}

.auth-card {
  width: 100%;
  max-width: 420px;
  padding: 12px 8px;
}

.title {
  margin: 0 0 4px;
  text-align: center;
  font-size: 24px;
  color: #303133;
}

.subtitle {
  margin: 0 0 28px;
  text-align: center;
  color: #909399;
  font-size: 14px;
}

.submit-btn {
  width: 100%;
}

.footer-link {
  text-align: center;
  font-size: 14px;
  color: #606266;
}

.footer-link a {
  color: #409eff;
  text-decoration: none;
}
</style>

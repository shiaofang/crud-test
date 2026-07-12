<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { User, Lock } from "@element-plus/icons-vue";
import type { FormInstance, FormRules } from "element-plus";
import { useAuth } from "../composables/useAuth";

const route = useRoute();
const router = useRouter();
const auth = useAuth();

const formRef = ref<FormInstance>();
const loading = ref(false);

const form = reactive({
  username: "",
  password: "",
});

const rules: FormRules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
};

async function submit() {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    try {
      await auth.login(form.username, form.password);
      ElMessage.success("登录成功");
      const redirect = (route.query.redirect as string) || "/";
      router.push(redirect);
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "登录失败";
      ElMessage.error(typeof msg === "string" ? msg : "登录失败");
    } finally {
      loading.value = false;
    }
  });
}
</script>

<template>
  <div class="auth-page">
    <el-card shadow="never" class="auth-card">
      <h2 class="title">登录悦购商城</h2>
      <p class="subtitle">欢迎回来，请登录您的账号</p>

      <el-form ref="formRef" :model="form" :rules="rules" label-width="0" size="large">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名">
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            show-password
            @keyup.enter="submit"
          >
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" class="submit-btn" @click="submit">
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="footer-link">
        还没有账号？
        <router-link to="/register">立即注册</router-link>
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

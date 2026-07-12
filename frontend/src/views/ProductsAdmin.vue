<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import type { FormInstance, FormRules } from "element-plus";
import { Plus, Search } from "@element-plus/icons-vue";
import { productApi } from "../api";
import type { Product, ProductPayload } from "../types";

const loading = ref(false);
const products = ref<Product[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(10);
const keyword = ref("");

const dialogVisible = ref(false);
const dialogTitle = ref("");
const editingId = ref<number | null>(null);
const formRef = ref<FormInstance>();
const submitting = ref(false);

const form = reactive<ProductPayload>({
  name: "",
  description: "",
  price: 0,
  stock: 0,
});

const rules: FormRules = {
  name: [{ required: true, message: "请输入商品名称", trigger: "blur" }],
  price: [{ required: true, message: "请输入价格", trigger: "blur" }],
  stock: [{ required: true, message: "请输入库存", trigger: "blur" }],
};

async function fetchData() {
  loading.value = true;
  try {
    const res = await productApi.list({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    });
    products.value = res.items;
    total.value = res.total;
  } catch {
    ElMessage.error("加载数据失败，请检查后端服务");
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  fetchData();
}

function openCreate() {
  dialogTitle.value = "新增商品";
  editingId.value = null;
  Object.assign(form, { name: "", description: "", price: 0, stock: 0 });
  dialogVisible.value = true;
}

function openEdit(row: Product) {
  dialogTitle.value = "编辑商品";
  editingId.value = row.id;
  Object.assign(form, {
    name: row.name,
    description: row.description ?? "",
    price: Number(row.price),
    stock: row.stock,
  });
  dialogVisible.value = true;
}

async function submitForm() {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    submitting.value = true;
    try {
      const payload: ProductPayload = { ...form };
      if (editingId.value === null) {
        await productApi.create(payload);
        ElMessage.success("新增成功");
      } else {
        await productApi.update(editingId.value, payload);
        ElMessage.success("更新成功");
      }
      dialogVisible.value = false;
      fetchData();
    } catch {
      ElMessage.error("保存失败，请确认已登录");
    } finally {
      submitting.value = false;
    }
  });
}

async function handleDelete(row: Product) {
  try {
    await ElMessageBox.confirm(`确定删除商品「${row.name}」吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await productApi.remove(row.id);
    ElMessage.success("删除成功");
    if (products.value.length === 1 && page.value > 1) page.value -= 1;
    fetchData();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败");
  }
}

onMounted(fetchData);
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="header">
          <span class="title">商品管理</span>
          <div class="actions">
            <el-input
              v-model="keyword"
              placeholder="按名称搜索"
              clearable
              style="width: 220px"
              @keyup.enter="handleSearch"
              @clear="handleSearch"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-button type="primary" @click="handleSearch">搜索</el-button>
            <el-button type="success" @click="openCreate">
              <el-icon><Plus /></el-icon>新增
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="products" v-loading="loading" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="商品名称" min-width="140" />
        <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
        <el-table-column prop="price" label="价格" width="110">
          <template #default="{ row }">￥{{ Number(row.price).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="stock" label="库存" width="90" />
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ row.created_at?.replace("T", " ").slice(0, 19) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row as Product)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row as Product)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next"
          :total="total"
          :current-page="page"
          :page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          @current-change="(p: number) => { page = p; fetchData(); }"
          @size-change="(s: number) => { pageSize = s; page = 1; fetchData(); }"
        />
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入商品名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请输入描述" />
        </el-form-item>
        <el-form-item label="价格" prop="price">
          <el-input-number v-model="form.price" :min="0" :precision="2" :step="1" />
        </el-form-item>
        <el-form-item label="库存" prop="stock">
          <el-input-number v-model="form.stock" :min="0" :step="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page {
  max-width: 1100px;
  margin: 24px auto;
  padding: 0 16px;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.title {
  font-size: 18px;
  font-weight: 600;
}
.actions {
  display: flex;
  gap: 8px;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>

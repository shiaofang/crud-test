import { createRouter, createWebHistory } from "vue-router";
import { useAuth } from "../composables/useAuth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "home",
      component: () => import("../views/Home.vue"),
    },
    {
      path: "/login",
      name: "login",
      component: () => import("../views/Login.vue"),
      meta: { guestOnly: true },
    },
    {
      path: "/register",
      name: "register",
      component: () => import("../views/Register.vue"),
      meta: { guestOnly: true },
    },
    {
      path: "/admin/products",
      name: "admin-products",
      component: () => import("../views/ProductsAdmin.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/admin/hot-products",
      name: "admin-hot-products",
      component: () => import("../views/HotProductsAdmin.vue"),
      meta: { requiresAuth: true },
    },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuth();
  if (!auth.initialized.value) {
    await auth.init();
  }
  if (to.meta.requiresAuth && !auth.isLoggedIn.value) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.meta.guestOnly && auth.isLoggedIn.value) {
    return { name: "home" };
  }
});

export default router;

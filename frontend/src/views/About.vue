<script setup lang="ts">
const stacks = [
  {
    title: "前端",
    items: [
      "Vue 3（Composition API + <script setup>）",
      "TypeScript 类型约束",
      "Vite 开发与构建",
      "Element Plus UI 组件库",
      "Vue Router 路由与登录守卫",
      "Axios 封装 HTTP；EventSource / fetch SSE",
    ],
  },
  {
    title: "后端",
    items: [
      "Python 3 + FastAPI",
      "SQLAlchemy 2.x ORM",
      "Pydantic / pydantic-settings 校验与配置",
      "PyMySQL 连接 MySQL；aiokafka 连接 Kafka",
      "python-jose + bcrypt（JWT / 密码哈希）",
      "LangChain + ChatOllama（工具调用与流式输出）",
    ],
  },
  {
    title: "基础设施",
    items: [
      "MySQL 8（users / products / activities）",
      "Apache Kafka（KRaft 单节点，商品动态总线）",
      "Docker Compose 本地一键启动",
      "Nginx 静态资源 + /api 反向代理",
      "GitHub Actions + GHCR 构建与部署",
    ],
  },
];

const modules = [
  {
    name: "frontend/src",
    desc: "页面（含首页实时动态）、路由、API 封装、鉴权 composable、智能助手组件、数据刷新事件。",
  },
  {
    name: "backend/app/routers",
    desc: "HTTP 路由：auth、products、chat、activities、health。",
  },
  {
    name: "backend/app/kafka_bus.py + activity_hub.py",
    desc: "商品动态：Kafka Producer/Consumer、落库、内存扇出到 SSE 订阅者。",
  },
  {
    name: "backend/app/llm.py + tools/",
    desc: "助手编排：系统提示、工具循环、SSE 事件；商品/用户 StructuredTool 与登录上下文。",
  },
  {
    name: "docker / CI",
    desc: "docker-compose 编排 MySQL + Kafka + 后端 + Nginx；Actions 构建镜像并 SSH 部署。",
  },
];

const highlights = [
  {
    title: "Agent 落地，而不只是「调一下 Chat API」",
    points: [
      "LangChain ChatOllama + StructuredTool：模型决定何时调工具、传什么参数。",
      "多轮工具循环（有上限）：流式输出 → tool_calls → ToolMessage 回填 → 再总结回复。",
      "SSE 双通道：status / status_delta 展示思考与工具过程，delta 展示最终中文回复。",
    ],
  },
  {
    title: "鉴权贯穿 HTTP 与 Agent 两层",
    points: [
      "REST 写接口靠 JWT；助手侧用 get_current_user_optional + ContextVar 绑定本轮用户。",
      "全部业务工具执行前校验登录，未登录意图写库时短路提示。",
      "单轮写操作上限（MAX_WRITES_PER_REQUEST），降低一次对话批量误改风险。",
    ],
  },
  {
    title: "Kafka 实时动态，管理端与 AI 同源展示",
    points: [
      "商品创建/更新/删除后发 Kafka 事件，Consumer 写入 activities 并经 ActivityHub 扇出。",
      "首页 SSE 订阅 /api/activities/stream，区分「管理」与「AI」来源。",
      "启动时从 MySQL 回填近期动态，新连接也能先看到最近记录。",
    ],
  },
  {
    title: "前后端与部署形成闭环",
    points: [
      "写库成功后 SSE done.refresh 广播，管理页按资源名选择性刷新。",
      "工具在 asyncio.to_thread + 短生命周期 Session 中执行，避免阻塞事件循环与跨线程复用 Session。",
      "Docker Compose（含 Kafka）+ GHCR + Actions：PR 只构建校验，main 才按 commit sha 不可变部署。",
    ],
  },
];

const features = [
  {
    title: "首页",
    points: [
      "系统入口，并展示基于 Kafka 的商品操作实时动态（管理端 / AI 助手）。",
      "EventSource 订阅 /api/activities/stream；断线自动重连提示。",
    ],
  },
  {
    title: "商品管理",
    points: [
      "登录后进入「商品管理」：分页列表、关键字筛选、新增 / 编辑 / 删除。",
      "后端 products 路由写操作依赖 get_current_user，未登录返回 401。",
      "写库成功后发 Kafka 动态；助手写库还会通知前端刷新列表。",
    ],
  },
  {
    title: "用户注册 / 登录",
    points: [
      "注册校验用户名、密码、可选邮箱；密码 bcrypt 哈希后入库。",
      "登录签发 JWT，前端存 Token，请求头带 Authorization: Bearer。",
      "路由守卫：需登录页强制跳转登录；已登录访问登录/注册则回首页。",
      "用户增删改查无独立管理页，仅通过 AI 助手工具完成。",
    ],
  },
  {
    title: "AI 智能助手",
    points: [
      "右下角悬浮入口，可拖拽调整面板大小；发送新消息可 abort 上一请求。",
      "自然语言对话；模型通过 Tool Calling 调用商品 / 用户业务工具。",
      "增删改查商品/用户需登录，否则直接提示登录。",
      "流式输出：思考过程与最终回复分区展示；写商品同样进入首页动态流。",
    ],
  },
  {
    title: "容器化与 CI/CD",
    points: [
      "本地：docker compose up 启动 MySQL、Kafka、后端、Nginx。",
      "生产：push main → Actions 构建并推送 GHCR 镜像 → SSH 到服务器 pull & up。",
      "PR 仅构建校验，不推送、不部署；镜像打 latest + commit sha 标签。",
    ],
  },
];

const implSections = [
  {
    title: "1. 整体架构与请求链路",
    paragraphs: [
      "采用前后端分离：浏览器加载 Vue 单页应用，业务数据一律走 /api。开发时 Vite 将 /api 代理到本机 FastAPI；生产环境由 Nginx 同域反向代理到 backend:8000，避免跨域，也方便配置 SSE 不缓冲。",
      "后端按分层组织：routers 处理 HTTP，schemas 做入参/出参校验，crud 访问数据库，dependencies 注入会话与当前用户。启动时 create_all 建表，并拉起 Kafka 动态总线。",
    ],
  },
  {
    title: "2. 前端实现要点",
    paragraphs: [
      "页面用 Vue 3 + Element Plus；鉴权状态集中在 useAuth（Token、当前用户、登录/退出）。Axios 实例统一加 Token、处理错误。",
      "首页用 EventSource 订阅商品动态 SSE；智能助手用 fetch 解析 /api/chat：delta（正文）、status / status_delta（思考过程）、done（结束与 refresh）。收到 refresh 后通过 useDataRefresh 广播，商品管理页按资源名选择性重新拉数。",
      "路由 meta.requiresAuth / guestOnly 配合 beforeEach，保证管理页与访客页权限一致。",
    ],
  },
  {
    title: "3. 后端 API 与数据模型",
    paragraphs: [
      "核心表：users（用户名、邮箱、密码哈希）、products（名称、描述、价格、库存等）、activities（商品操作动态持久化）。",
      "公开接口：健康检查、商品读接口、动态 SSE。写操作依赖 JWT。接口文档可在后端启动后访问 /docs（Swagger）。",
    ],
  },
  {
    title: "4. 鉴权与权限设计",
    paragraphs: [
      "登录成功返回 access_token；后续请求由 HTTPBearer 解析，dependencies.get_current_user / get_current_user_optional 还原用户。密码不明文存储，使用 bcrypt。",
      "助手侧用 ContextVar 绑定本轮 db 与 current_user。业务工具在执行前检查登录态；未登录且意图为增删改查时，llm 层会短路提示登录。",
    ],
  },
  {
    title: "5. 智能助手（Tool Calling + SSE）",
    paragraphs: [
      "ChatOllama 绑定 StructuredTool（商品 CRUD、用户 CRUD）。系统提示注入当前登录状态，约束未登录时不得追问写库字段、不得假装可写库。",
      "chat_stream 多轮工具循环：模型流式输出 → 若有 tool_calls 则执行工具并把 ToolMessage 回填 → 再让模型总结。事件以 SSE 推给前端：status 展示「正在思考 / 调用工具…」，delta 展示最终中文回复。Nginx 对 /api/ 关闭 proxy_buffering，保证流式实时到达。",
      "写操作有单轮次数上限，避免一次对话批量误操作；工具在独立线程短 Session 中执行。前端发送新消息时可 abort 上一请求，后端配合断开检测，降低后台继续写库的风险。",
    ],
  },
  {
    title: "6. 商品动态（Kafka + SSE）",
    paragraphs: [
      "管理端 REST 或助手工具写商品成功后，kafka_bus 向 topic（默认 mall.activities）发送事件，区分 source=admin / ai。",
      "Consumer 将事件写入 activities 表，再经 ActivityHub 推给所有 /api/activities/stream 订阅者；启动时从 MySQL 回填近期记录到内存 Hub。",
      "本地开发需先起 Kafka（可用 docker compose up -d kafka）；动态能力依赖 Kafka，不做本机 hub 降级。",
    ],
  },
  {
    title: "7. 部署与运维",
    paragraphs: [
      "Docker：backend 镜像跑 uvicorn；frontend Dockerfile 多阶段 npm build，产物打进 nginx 镜像。Compose 串联 MySQL、Kafka、backend、nginx，环境变量区分本地与生产。",
      "CI/CD：Actions 用 Buildx 构建 backend 与 nginx 镜像，打 latest 与 commit sha 标签推到 GHCR；部署 job SSH 到服务器按 sha 拉取并 compose up -d。Secrets 管理服务器地址、SSH 密钥、DB 密码、JWT、CORS、Ollama Key、拉镜像 Token 等。",
    ],
  },
];

const tradeoffs = [
  {
    title: "已做的取舍",
    points: [
      "首页以实时动态为主入口展示，商品 CRUD 集中在管理页与助手。",
      "用户管理不做独立后台页，刻意走助手工具，突出「自然语言操作业务」这条演示主线。",
      "当前无角色权限（RBAC）：任意登录用户权限相同，适合演示，生产需按角色拆分。",
      "商品动态必须连上 Kafka，不做无消息中间件时的本机降级。",
    ],
  },
  {
    title: "后续可扩展",
    points: [
      "自动化测试：pytest 覆盖 auth / crud / 工具鉴权；前端关键路径或 E2E。",
      "安全加固：HTTPS、登录与 /chat 限流、Refresh Token 或 HttpOnly Cookie、细粒度 RBAC。",
      "业务完善：结构化日志与 LLM 调用观测、数据库正式迁移工具、Kafka 多副本与监控。",
    ],
  },
];
</script>

<template>
  <div class="about">
    <section class="hero">
      <div class="hero-inner">
        <h1>项目介绍</h1>
        <p>
          智能商城管理系统是一套可本地运行、可 Docker 部署的全栈项目：登录后管理商品，
          集成基于大模型工具调用（Tool Calling）的 AI 助手，并以 Kafka + SSE
          展示商品操作实时动态，配套 GitHub Actions 自动构建与发布。
        </p>
      </div>
    </section>

    <section class="block">
      <h2>项目亮点</h2>
      <p class="lead">在商品管理之外，重点实现了 AI 助手（Tool Calling + SSE）、Kafka 实时动态、双层鉴权，以及 Docker / CI/CD 发布链路。</p>
      <div class="feature-list">
        <div v-for="item in highlights" :key="item.title" class="feature-item">
          <h3>{{ item.title }}</h3>
          <ul>
            <li v-for="(p, i) in item.points" :key="i">{{ p }}</li>
          </ul>
        </div>
      </div>
    </section>

    <section class="block">
      <h2>技术栈</h2>
      <p class="lead">前端、后端与基础设施。</p>
      <div class="stack-grid">
        <div v-for="group in stacks" :key="group.title" class="stack-card">
          <h3>{{ group.title }}</h3>
          <ul>
            <li v-for="item in group.items" :key="item">{{ item }}</li>
          </ul>
        </div>
      </div>
    </section>

    <section class="block">
      <h2>仓库结构（核心）</h2>
      <div class="module-list">
        <div v-for="m in modules" :key="m.name" class="module-item">
          <code>{{ m.name }}</code>
          <span>{{ m.desc }}</span>
        </div>
      </div>
    </section>

    <section class="block">
      <h2>功能说明</h2>
      <div class="feature-list">
        <div v-for="item in features" :key="item.title" class="feature-item">
          <h3>{{ item.title }}</h3>
          <ul>
            <li v-for="(p, i) in item.points" :key="i">{{ p }}</li>
          </ul>
        </div>
      </div>
    </section>

    <section class="block">
      <h2>实现方式（详细）</h2>
      <div class="impl-list">
        <article v-for="sec in implSections" :key="sec.title" class="impl-item">
          <h3>{{ sec.title }}</h3>
          <p v-for="(para, i) in sec.paragraphs" :key="i">{{ para }}</p>
        </article>
      </div>
    </section>

    <section class="block">
      <h2>请求与数据流</h2>
      <pre class="arch">用户浏览器
  │
  ├─ 页面路由（Vue Router + 登录守卫）
  ├─ REST：Axios → /api/* → Nginx → FastAPI → MySQL
  │
  ├─ 助手对话：fetch SSE /api/chat
  │     → FastAPI chat_stream
  │     → LangChain + Ollama（可能多轮 Tool Calling）
  │     → tools（ContextVar 注入 db / 当前用户）
  │     → 写库成功则 SSE done.refresh 通知前端刷新
  │
  └─ 首页动态：EventSource SSE /api/activities/stream
        ← ActivityHub 扇出
        ← Kafka Consumer 落库 activities
        ← Producer（管理端 / 助手写商品）</pre>
    </section>

    <section class="block">
      <h2>权限一览</h2>
      <div class="perm-table-wrap">
        <table class="perm-table">
          <thead>
            <tr>
              <th>能力</th>
              <th>未登录</th>
              <th>已登录</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>浏览首页 / 实时动态</td>
              <td>可以</td>
              <td>可以</td>
            </tr>
            <tr>
              <td>商品管理页 CRUD</td>
              <td>不可（跳转登录）</td>
              <td>可以</td>
            </tr>
            <tr>
              <td>助手增删改查商品 / 用户</td>
              <td>提示先登录</td>
              <td>可以（工具调用）</td>
            </tr>
            <tr>
              <td>用户管理独立后台页</td>
              <td>无</td>
              <td>无（仅助手工具）</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="block">
      <h2>设计取舍与可扩展</h2>
      <p class="lead">当前实现边界，以及后续可继续完善的方向。</p>
      <div class="feature-list">
        <div v-for="item in tradeoffs" :key="item.title" class="feature-item">
          <h3>{{ item.title }}</h3>
          <ul>
            <li v-for="(p, i) in item.points" :key="i">{{ p }}</li>
          </ul>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.about {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 0 24px 56px;
  box-sizing: border-box;
}

.hero {
  margin: 24px 0 8px;
  padding: 36px 32px;
  border-radius: 16px;
  background: linear-gradient(135deg, #3a8ee6 0%, #2b6cb0 100%);
  color: #fff;
}

.hero h1 {
  margin: 0 0 12px;
  font-size: 28px;
  font-weight: 700;
}

.hero p {
  margin: 0;
  max-width: 720px;
  line-height: 1.75;
  font-size: 15px;
  opacity: 0.95;
}

.block {
  margin-top: 36px;
}

.block h2 {
  margin: 0 0 10px;
  font-size: 20px;
  color: #303133;
  padding-left: 10px;
  border-left: 4px solid #409eff;
}

.lead {
  margin: 0 0 16px;
  font-size: 14px;
  color: #909399;
  line-height: 1.6;
}

.stack-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.stack-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  padding: 18px 20px;
}

.stack-card h3 {
  margin: 0 0 12px;
  font-size: 16px;
  color: #409eff;
}

.stack-card ul {
  margin: 0;
  padding-left: 18px;
  color: #606266;
  line-height: 1.75;
  font-size: 13px;
}

.module-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.module-item {
  display: grid;
  grid-template-columns: minmax(160px, 220px) 1fr;
  gap: 12px;
  align-items: start;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  padding: 14px 18px;
  font-size: 14px;
  color: #606266;
  line-height: 1.6;
}

.module-item code {
  font-size: 13px;
  color: #409eff;
  background: #ecf5ff;
  padding: 2px 8px;
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.feature-list,
.impl-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.feature-item,
.impl-item {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  padding: 16px 20px;
}

.feature-item h3,
.impl-item h3 {
  margin: 0 0 8px;
  font-size: 15px;
  color: #303133;
}

.feature-item ul {
  margin: 0;
  padding-left: 18px;
  color: #606266;
  font-size: 14px;
  line-height: 1.7;
}

.impl-item p {
  margin: 0 0 10px;
  font-size: 14px;
  line-height: 1.75;
  color: #606266;
}

.impl-item p:last-child {
  margin-bottom: 0;
}

.arch {
  margin: 0;
  padding: 20px 24px;
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.75;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.perm-table-wrap {
  overflow-x: auto;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 12px;
}

.perm-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.perm-table th,
.perm-table td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid #ebeef5;
  color: #606266;
}

.perm-table th {
  background: #f5f7fa;
  color: #303133;
  font-weight: 600;
}

.perm-table tr:last-child td {
  border-bottom: none;
}

@media (max-width: 768px) {
  .stack-grid {
    grid-template-columns: 1fr;
  }

  .module-item {
    grid-template-columns: 1fr;
    gap: 6px;
  }

  .hero {
    padding: 28px 20px;
  }

  .hero h1 {
    font-size: 24px;
  }
}
</style>

# 系统运行手册（公开代码版）

本目录包含家具企业顾问 Agent 的后端、前端、数据库编排和本地启动器。公开版本不附带企业资料、内部评测数据、数据库、索引或密钥；`seed_demo_*` 只创建合成本地演示数据。

## 1. 环境与端口

- Windows 10/11、PowerShell 5.1+
- Python 3.11、Node.js 20+
- Docker Desktop（Linux containers）
- 默认端口：数据库 `54329`、后端 `8000`、前端 `5173`

## 2. 配置

在 `system` 目录执行：

```powershell
Copy-Item .env.example .env
```

| 配置项 | 用途 |
| --- | --- |
| `POSTGRES_PASSWORD` | PostgreSQL 本地密码 |
| `DATABASE_URL` | 后端连接串；特殊字符需 URL 编码 |
| `JWT_SECRET` | 令牌签名密钥，至少 32 字节随机值 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 登录令牌有效时间 |
| `DEMO_*_PASSWORD` | 三个演示账号的初始化密码 |
| `EMBEDDING_PROVIDER/MODEL` | 向量服务类型和模型 |
| `EMBEDDING_LOCAL_FILES_ONLY` | `true` 只用缓存；`false` 允许下载 |
| `EMBEDDING_DEVICE` | 推理设备，默认 `cpu` |
| `RAG_TOP_K_*` | 默认及最大检索数量 |
| `RAG_MIN_SIMILARITY` | 最低向量相似度 |
| `RAG_CONTEXT_MAX_CHARS` | 生成上下文长度上限 |
| `LLM_BASE_URL/API_KEY` | OpenAI 兼容接口和密钥 |
| `LLM_ROUTER_MODEL` | 意图路由模型 |
| `LLM_GENERATION_MODEL` | 回答生成模型 |
| `LLM_TIMEOUT_SECONDS` | 模型请求超时 |

```powershell
[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
```

不要在提交、截图、日志或 Issue 中公开 `.env` 内容。

### 本地 embedding

默认模型是 `BAAI/bge-small-zh-v1.5`。本机没有缓存时，将 `EMBEDDING_LOCAL_FILES_ONLY=false` 以允许首次下载；缓存成功后可改回 `true`。首次资料解析通常较慢。变更模型或向量维度后，不应混用旧索引，应以一致配置重新导入对应资料。

## 3. 安装

```powershell
Set-Location backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"

Set-Location ..\frontend
npm ci
Set-Location ..
```

## 4. 数据库

```powershell
docker compose up -d --wait db
Set-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

迁移只建立当前代码所需结构，公开仓库不含业务资料或历史数据库。

## 5. 演示初始化

在 `system/backend` 运行：

```powershell
# 账号
.\.venv\Scripts\python.exe scripts\seed_demo_users.py

# 可选：合成产品及价格，产品必须先导入
.\.venv\Scripts\python.exe scripts\seed_demo_data.py
.\.venv\Scripts\python.exe scripts\seed_demo_prices.py
```

账号为 `admin_demo`（ADMIN）、`pm_demo`（PRODUCT_MANAGER）和 `sales_demo`（SALES）。密码从 `.env` 读取；脚本不会输出或覆盖已有同名账号的密码。

## 6. 启动

### 推荐启动器

启动器要求已存在：

- `system/.env`
- `system/backend/.venv/Scripts/python.exe`
- `system/frontend/node_modules/vite/bin/vite.js`
- 已启动的 Docker Desktop
- 最新 Alembic 迁移

在仓库根目录执行：

```powershell
# 只读预检
.\start-system.ps1 -Check

# 启动并打开登录页
.\一键启动.cmd

# 启动但不打开浏览器
.\start-system.ps1 -NoBrowser

# 停止启动器拥有的前后端
.\start-system.ps1 -Stop
```

预检会检查配置、应用导入、数据库、迁移 head、pgvector 和 Node.js；不会迁移、导入资料或调用 embedding/外部大模型。停止时保留数据库和上传资料。若端口由其他程序占用，启动器会保留该程序并报错。

### 手动启动

终端一（`system/backend`）：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

终端二（`system/frontend`）：

```powershell
npm run dev -- --host 127.0.0.1 --port 5173
```

- 登录页：<http://127.0.0.1:5173/login>
- 后端：<http://127.0.0.1:8000>
- 健康检查：<http://127.0.0.1:8000/api/health>

## 7. 角色与使用流程

- **ADMIN**：用户、资料权限和审计管理；
- **PRODUCT_MANAGER**：产品与资料维护、业务内容检查；
- **SALES**：顾问问答及授权范围内的资料和价格查询。

最终权限以后端 RBAC 和资料授权为准，不要只依据前端菜单。

资料导入流程：

1. 用具备资料管理权限的账号登录；
2. 在产品管理中建立关联产品；
3. 上传 PDF、DOCX 或 XLSX；
4. 设置资料名称、密级、允许角色和关联产品；
5. 等待后台提取、切片和 embedding 完成；
6. 在顾问界面提问并核对引用。

`LLM_API_KEY` 为空或接口不可达时，依赖模型的步骤会失败或进入受限降级路径。健康检查通过只证明应用、数据库和 pgvector 可用，不代表外部模型调用正常。

## 8. 测试与构建

```powershell
Set-Location system\backend
.\.venv\Scripts\python.exe -m pytest

Set-Location ..\frontend
npm test
npm run build
```

不要把上传资料、数据库导出、模型缓存或真实调用日志加入测试夹具。

## 9. 常见问题

### `Missing prerequisite`

按报错补齐 `.env`、后端虚拟环境或前端依赖，再执行 `-Check`。启动器不代替首次安装。

### 数据库连接失败

```powershell
docker compose ps
docker compose up -d --wait db
```

确认 Docker 使用 Linux engine，且 `POSTGRES_PASSWORD` 与 `DATABASE_URL` 一致。

### `SCHEMA_NOT_CURRENT`

在 `system/backend` 执行：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### `PGVECTOR_MISSING`

确认使用仓库提供的 Compose 数据库。普通 PostgreSQL 镜像不一定安装 pgvector。

### 端口被占用

关闭占用 8000/5173 的程序。启动器使用固定端口，不会结束不属于它的进程。

### 资料长期处于解析中

查看后端输出或 `system/.codex-artifacts/launcher/backend.err.log`，检查模型缓存、`EMBEDDING_LOCAL_FILES_ONLY`、网络和文件格式。

### 顾问回答失败

检查 `LLM_BASE_URL`、`LLM_API_KEY`、模型名和网络。资料未解析、权限不足或检索无结果时也可能没有可引用内容。

### 登录失败

确认已迁移数据库并执行 `seed_demo_users.py`。该脚本不会覆盖已有同名账号的密码。

## 10. 安全提示

- 不提交 `.env`、上传文件、数据库、向量索引、模型缓存或运行日志；
- 正式导入前确认资料使用权、密级和允许角色；
- 生产环境应替换演示账号，强化密钥、网络和备份管理；
- 对外使用回答前核对引用，模型内容不自动等同企业正式口径。

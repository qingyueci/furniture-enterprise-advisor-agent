# 家具企业顾问 Agent（公开代码版）

面向家具企业产品资料、报价与业务规则核对场景的全栈 Agent 原型，集成产品管理、资料解析、权限控制、检索增强问答（RAG）、报价查询和审计日志。

> 公开仓库只提供通用代码和合成演示种子，不含可直接使用的企业知识库。部署后需自行配置模型服务并导入有权使用的资料。

## 主要功能

- **账号与角色权限**：管理员、产品经理、销售三类角色；
- **产品与价格管理**：维护产品目录、型号和多类价格；
- **资料上传与解析**：支持 PDF、DOCX、XLSX，后台切片并生成向量；
- **顾问问答**：按权限检索资料，回答附带可追溯引用；
- **规则和报价核对**：区分产品事实、业务规则、公开价格与内部报价；
- **审计日志**：记录登录、资料访问、Agent 调用和权限操作。

## 技术组成

- 后端：FastAPI、SQLAlchemy、Alembic、PostgreSQL + pgvector
- 前端：Vue 3、TypeScript、Vite、Element Plus、Pinia
- 向量模型：默认 `BAAI/bge-small-zh-v1.5`
- 大模型：OpenAI 兼容接口；示例配置指向 DeepSeek

## 环境要求

- Windows 10/11、Python 3.11、Node.js 20+
- Docker Desktop（Linux containers）
- 首次下载本地 embedding 模型所需的网络，或现有本地缓存
- 完整顾问生成链路所需的外部大模型 API Key

## 快速开始

以下命令均在 PowerShell 中执行。

### 1. 获取代码并配置

```powershell
git clone https://github.com/qingyueci/furniture-enterprise-advisor-agent.git
Set-Location furniture-enterprise-advisor-agent
Copy-Item system\.env.example system\.env
```

编辑 `system/.env`，至少替换：

- `POSTGRES_PASSWORD` 和 `DATABASE_URL` 中对应的 URL 编码密码；
- 至少 32 字节的 `JWT_SECRET`；
- 三个 `DEMO_*_PASSWORD`；
- 需要完整问答时填写 `LLM_API_KEY`。

生成随机密钥：

```powershell
[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
```

`system/.env` 已被 Git 忽略，请勿提交真实密码或密钥。

### 2. 安装依赖

```powershell
Set-Location system\backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"

Set-Location ..\frontend
npm ci
Set-Location ..\..
```

### 3. 初始化数据库

启动 Docker Desktop 后运行：

```powershell
Set-Location system
docker compose up -d --wait db
Set-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### 4. 初始化演示账号和合成数据

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo_users.py
.\.venv\Scripts\python.exe scripts\seed_demo_data.py
.\.venv\Scripts\python.exe scripts\seed_demo_prices.py
Set-Location ..\..
```

密码来自 `.env`，脚本不会输出密码。演示账号：

| 用户名 | 角色 | 用途 |
| --- | --- | --- |
| `admin_demo` | ADMIN | 用户、权限、资料和审计管理 |
| `pm_demo` | PRODUCT_MANAGER | 产品与资料维护、顾问验证 |
| `sales_demo` | SALES | 顾问问答及授权范围内的查询 |

产品和价格种子完全合成，可选且可重复执行，不代表真实企业事实或报价。

### 5. 启动

```powershell
.\start-system.ps1 -Check
.\一键启动.cmd
```

- 登录页：<http://127.0.0.1:5173/login>
- 后端：<http://127.0.0.1:8000>
- 健康检查：<http://127.0.0.1:8000/api/health>

```powershell
# 启动但不打开浏览器
.\start-system.ps1 -NoBrowser

# 只停止启动器创建的前后端，保留数据库和资料
.\start-system.ps1 -Stop
```

详细安装、手动启动和故障排查见 [system/README.md](system/README.md)。

## 基本使用流程

1. 使用管理员账号登录，检查用户和角色。
2. 在产品管理中创建产品目录。
3. 在资料管理中上传 PDF、DOCX 或 XLSX，设置密级、允许角色和关联产品。
4. 等待解析完成；首次使用本地 embedding 时可能需要下载模型。
5. 进入顾问界面提问，核对回答、引用来源和权限边界。
6. 管理员可在审计日志中追踪关键操作。

建议先用合成或已脱敏资料验证。资料可见性由后端权限和上传时的授权范围共同决定。

## 测试与构建

```powershell
Set-Location system\backend
.\.venv\Scripts\python.exe -m pytest

Set-Location ..\frontend
npm test
npm run build
```

## 目录

```text
.
├─ system/
│  ├─ backend/            # API、Agent、RAG、权限、迁移和测试
│  ├─ frontend/           # Vue 管理端与顾问界面
│  ├─ docker-compose.yml  # PostgreSQL + pgvector
│  └─ .env.example        # 安全配置模板
├─ start-system.ps1       # Windows 启动、预检和停止入口
└─ 一键启动.cmd           # 双击入口
```

## 数据与安全边界

公开仓库不含：

- 企业资料、脱敏资料、上传文件、数据库和向量索引；
- 内部评测题集、真实调用记录、检索快照和验证输出；
- 论文、答辩材料、个人文档和本机路径；
- API Key、JWT 密钥、数据库密码和模型缓存。

部署者应自行完成资料授权、访问控制、备份和密钥管理，不要提交 `.env`、上传资料或运行时数据。模型生成内容不应自动视为企业正式口径。

## 许可证

当前仓库未附带许可证文件。在获得适当授权前，默认不授予复制、修改、分发或商业使用许可。

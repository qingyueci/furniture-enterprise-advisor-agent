# 系统运行说明（公开代码版）

本目录包含家具企业顾问 Agent 的前后端实现。公开版本不带原始资料、脱敏资料、内部评测数据、数据库、索引和 API 密钥；`seed_demo_*` 仅包含完全合成的 DEMO 功能种子。

## 依赖

- Windows 10/11
- Python 3.11
- Node.js 20+
- Docker Desktop（Linux containers）

## 配置

```powershell
Copy-Item .env.example .env
```

然后在 `.env` 中填写本地数据库密码、JWT_SECRET 和模型服务配置。`.env` 已被 Git 忽略，禁止提交真实密钥。

## 安装

```powershell
# 后端
Set-Location backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"

# 前端
Set-Location ..\frontend
npm ci
```

## 数据库与服务

```powershell
Set-Location ..
docker compose up -d --wait db
Set-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

也可以在仓库根目录运行 `一键启动.cmd`，它会执行配置预检并启动本地前后端。

## 测试

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest
```

测试使用 Mock 或空数据库，不应把本地上传资料、数据库文件和模型缓存加入版本控制。

## 资料导入

公开版本保留资料解析、权限和检索代码，但 `backend/data` 为空。请使用自己的资料进行本地导入；上传文件和运行时数据位于被忽略的本地目录，不会随仓库发布。

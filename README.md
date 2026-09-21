# 家具企业顾问 Agent（公开代码版）

面向家具企业产品资料、报价和规则核对场景的全栈 Agent 原型。公开副本仅保留通用实现、数据库迁移、前后端代码和可复用的演示脚本。

## 公开边界

以下内容没有纳入公开仓库：

- 原始企业资料、脱敏资料、内部评测数据集、上传文件、数据库和向量索引；
- 评测题集、真实调用记录、检索快照、验证输出和内部工作产物；
- 论文、答辩材料、个人文档、机器本地路径和环境文件；
- API Key、JWT 密钥、数据库密码和本地模型缓存。

代码中的 `DEMO_*` 产品和价格是完全合成的功能演示种子，不代表任何企业资料或商业报价。

## 目录

- `system/backend`：FastAPI、SQLAlchemy、Alembic、RAG 和权限控制；
- `system/frontend`：Vue 3 + Vite 管理界面与顾问界面；
- `system/docker-compose.yml`：本地 pgvector 数据库；
- `start-system.ps1`、`一键启动.cmd`：Windows 本地启动入口。

## 本地运行

1. 复制 `system/.env.example` 为 `system/.env`，只填写本地配置和密钥，不要提交该文件。
2. 在 `system/backend` 创建 Python 3.11 虚拟环境并安装依赖：

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -e ".[test]"
   ```

3. 安装前端依赖：

   ```powershell
   Set-Location system/frontend
   npm ci
   ```

4. 启动 Docker Desktop 后，在仓库根目录运行：

   ```powershell
   .\一键启动.cmd
   ```

应用默认使用本机 `127.0.0.1`，首次运行前需完成数据库迁移。公开副本没有内置企业资料；需要在本地通过资料上传界面导入自己的资料后，才会产生知识库内容。

## 许可证

当前仓库未附带额外许可证。使用前请根据你的发布和授权需求补充许可证文件。

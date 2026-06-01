# 贡献指南

感谢您对 TrailSnap 的贡献！本文档将帮助您了解如何参与项目开发。

## 目录

- [开发环境设置](#开发环境设置)
- [代码规范](#代码规范)
- [提交规范](#提交规范)
- [Pull Request 流程](#pull-request-流程)
- [组件开发指南](#组件开发指南)
- [数据库迁移](#数据库迁移)
- [问题反馈](#问题反馈)

## 开发环境设置

### 前置要求

- Node.js >= 18
- Python >= 3.10
- PostgreSQL 18 + pgvector
- Docker (可选)

### 1. Fork 仓库

点击 GitHub 页面右上角的 **Fork** 按钮，将仓库 Fork 到您的 GitHub 账户。

### 2. 克隆仓库

```bash
git clone https://github.com/<your-username>/TrailSnap.git
cd TrailSnap
```

### 3. 配置上游远程

```bash
git remote add upstream https://github.com/LC044/TrailSnap.git
```

### 4. 安装各组件依赖

**Frontend (Vue 3 + TypeScript + Vite)**
```bash
cd package/website
pnpm install
```

**Backend (FastAPI + SQLAlchemy)**
```bash
cd package/server
uv sync
```

**AI Service (FastAPI + PaddleOCR/InsightFace)**
```bash
cd package/ai
uv sync --extra cpu   # CPU 版本
# 或
uv sync --extra gpu   # GPU 版本 (CUDA 12.8)
```

### 5. 环境变量配置

在各组件目录下创建 `.env` 文件：

**Backend (`package/server/.env`)**
```env
DB_URL=postgresql://user:password@localhost:5432/trailsnap
AI_API_URL=http://localhost:8001
```

**AI Service (`package/ai/.env`)**
```env
# GPU 版本需要配置 CUDA
CUDA_VISIBLE_DEVICES=0
```

## 代码规范

### Python (Backend / AI Service)

- 遵循 **PEP 8** 规范
- 使用 **Black** 格式化代码
- 使用 **Ruff** 进行 linting
- 类型提示必须完整（函数参数、返回值）
- 所有 API 路由必须返回 `BaseResponse` 统一格式

```python
# 好的示例
async def get_photo(photo_id: int) -> BaseResponse[PhotoSchema]:
    photo = await crud.get_photo_by_id(photo_id)
    if not photo:
        return BaseResponse.fail(code=404, message="Photo not found")
    return BaseResponse.success(data=PhotoSchema.model_validate(photo))

# 不好的示例
async def get_photo(photo_id):
    return {"data": ...}  # 未使用统一响应格式
```

### TypeScript / Vue (Frontend)

- 遵循项目已有的代码风格
- 组件使用 `<script setup lang="ts">` 语法
- API 请求使用统一的请求封装
- 组件文件放在 `src/components/` 目录

### 数据库模型

- 所有数据库模型放在 `app/db/models/` 目录
- 使用 SQLAlchemy ORM
- 创建/修改模型后必须生成迁移文件

## 提交规范

### Commit Message 格式

```
<type>(<scope>): <subject>

<body>
```

**Type 类型：**
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档修改
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具相关

**Scope 示例：**
- `feat(photo)`: 照片功能
- `fix(album)`: 相册修复
- `docs(api)`: API 文档
- `refactor(backend)`: 后端重构

**示例：**
```
feat(photo): 添加照片评论功能

- 添加评论数据模型
- 实现评论 CRUD API
- 前端添加评论组件

Closes #123
```

### 提交前检查

```bash
# 后端代码格式化
cd package/server
ruff check . --fix
black .

# 前端代码检查
cd package/website
pnpm lint
```

## Pull Request 流程

### 1. 创建分支

从 `master` 分支创建功能分支：

```bash
git checkout master
git pull upstream master
git checkout -b feat/<your-feature-name>
```

### 2. 开发与提交

- 在新分支上进行开发
- 编写有意义的 commit message
- 确保代码通过 lint 检查

### 3. 推送分支

```bash
git push origin feat/<your-feature-name>
```

### 4. 创建 Pull Request

1. 访问原仓库，点击 **New Pull Request**
2. 选择您的分支与 `master` 分支对比
3. 填写 PR 描述：
   - 描述解决的问题或新增的功能
   - 列出主要的更改内容
   - 如有测试用例，说明如何测试
4. 关联相关 Issue（如果有）

### 5. PR 描述模板

```markdown
## 描述
<!-- 简述这次 PR 的目的 -->

## 更改内容
- <!-- 列出主要更改 -->

## 涉及组件
- [ ] Frontend
- [ ] Backend
- [ ] AI Service

## 测试
<!-- 说明如何测试这些更改 -->

## 截图（可选）
<!-- 如有 UI 更改，添加截图 -->
```

## 组件开发指南

### Frontend (`package/website`)

```bash
cd package/website
pnpm dev        # 开发服务器 http://localhost:5176
pnpm build      # 生产构建
pnpm preview    # 预览构建结果
pnpm lint       # 代码检查
```

**添加新组件：**
1. 组件放在 `src/components/` 目录
2. 页面放在 `src/views/` 目录
3. API 请求放在 `src/api/` 目录

### Backend (`package/server`)

```bash
cd package/server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**添加新 API：**
1. 在 `app/api/` 下创建或找到对应的路由文件
2. 在 `app/schemas/` 下定义请求/响应 Pydantic 模型
3. 在 `app/crud/` 下实现数据库操作
4. 在 `app/service/` 下编写业务逻辑

### AI Service (`package/ai`)

```bash
cd package/ai
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

**添加新 AI 能力：**
1. 在 `app/services/` 下实现 AI 处理逻辑
2. 在 `app/api/` 下添加对应的 API 端点
3. 模型文件放在 `data/models/` 目录

## 数据库迁移

使用 Alembic 管理数据库迁移：

```bash
cd package/server

# 创建迁移
alembic revision --autogenerate -m "description"

# 应用迁移
alembic upgrade head

# 查看当前版本
alembic current

# 回滚
alembic downgrade -1
```

**迁移注意事项：**
- 每次修改模型后生成迁移文件
- 提交前确保迁移能成功应用
- 删除字段使用 `drop_column`，不要直接删除

## 问题反馈

- **Bug 反馈**：请在 [GitHub Issues](https://github.com/LC044/TrailSnap/issues) 中提交
- **功能建议**：欢迎提交 Feature Request
- **安全漏洞**：请私信维护者，不要公开披露

## 许可证

贡献代码即表示您同意您的代码将在 [AGPLv3](LICENSE) 许可证下使用。

## 贡献者许可协议 (CLA)

在提交 Pull Request 之前，请确保您同意以下条款：

### 我同意以下内容：

1. **版权声明**：我声明我所贡献的代码是我原创的，或者我有权将该代码以相同的开源许可证贡献给本项目。

2. **开源许可**：我理解并同意，我的贡献将按照 [AGPLv3](LICENSE) 许可证发布。

3. **免责声明**：我理解贡献者不承担任何责任，代码按"原样"提供。

### 提交 PR

提交 Pull Request 时，请**在 PR 评论中回复**以下内容以留存记录：

```
I have read and agree to the CLA
```

> 注意：PR 创建时会自动显示 CLA 提示，请根据提示确认后再提交评论。

---

*感谢您的贡献！*
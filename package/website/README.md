# TrailSnap Frontend

TrailSnap 的前端应用，基于 Vue 3 + TypeScript + Vite 构建。

## 技术栈

- **框架**: Vue 3
- **语言**: TypeScript
- **构建工具**: Vite
- **UI 库**: Element Plus
- **CSS 框架**: TailwindCSS
- **状态管理**: Pinia
- **路由**: Vue Router

## 环境要求

- Node.js v18+ (推荐 v20 或 v22)
- pnpm (推荐) 或 npm/yarn

## 快速开始

### 1. 安装依赖

```bash
cd package/website

# 安装 pnpm
npm install -g pnpm

# 安装项目依赖
pnpm install
```

### 2. 运行开发服务器

```bash
pnpm run dev
```

启动后访问: http://localhost:5176

### 3. 构建生产版本

```bash
pnpm run build
```

构建产物将输出到 `dist` 目录。

## Android / iOS App（Capacitor）

原生容器使用 Capacitor，应用首次启动时会要求输入 TrailSnap 主后端地址。Docker
默认端口示例为 `http://192.168.1.10:8800`，不要在末尾添加 `/api`。局域网 HTTP
已在 Android/iOS 工程中启用，公网部署建议使用 HTTPS。

```bash
# 重新生成图标与启动图
pnpm mobile:assets

# 构建 Web 产物并同步 Android/iOS 工程
pnpm mobile:sync

# 安装 Android Studio/SDK 并设置 ANDROID_HOME 后构建 debug APK
pnpm android:build
```

APK 同时输出到 `android/app/build/outputs/apk/debug/app-debug.apk` 和
`artifacts/TrailSnap-0.9.0-debug.apk`。iOS 工程位于 `ios/App`，
需在 macOS + Xcode 上签名和构建。

GitHub Actions 会在手动运行 `Build Mobile App`、提交信息包含 `构建app`，或推送
`app-v*.*.*` 标签时构建 APK。手动运行时勾选 `publish`，或使用关键字/标签触发，
会同时创建带 APK 的 GitHub prerelease。

## 环境变量（暂不需要）

在根目录下创建 `.env` 或 `.env.local` 文件来配置环境变量：

```env
# 后端 API 地址 (开发环境通常由 Vite 代理转发)
VITE_API_BASE_URL=/api
```

## 目录结构

- `src/`
  - `api/`: API 请求封装
  - `assets/`: 静态资源
  - `components/`: 通用组件
  - `composables/`: 组合式函数 (Hooks)
  - `layouts/`: 布局组件
  - `router/`: 路由配置
  - `stores/`: Pinia 状态管理
  - `types/`: TS 类型定义
  - `views/`: 页面视图

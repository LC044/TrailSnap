# TrailSnap 官网 (Official Site)

这是 TrailSnap 项目的官方文档与落地页网站，基于 [VitePress](https://vitepress.dev/) 构建。

## 目录结构

```
package/official-site/
├── .vitepress/          # VitePress 配置与主题
│   ├── config.mts       # 核心配置文件
│   └── theme/           # 自定义主题 (暂无)
├── docs/                # 文档内容
│   ├── guide/           # 用户指南
│   └── dev/             # 开发者文档
├── index.md             # 首页 (Landing Page)
└── package.json         # 项目依赖
```

## 快速开始

### 1. 安装依赖

```bash
pnpm install
```

### 2. 本地开发

启动本地开发服务器，实时预览修改效果：

```bash
pnpm run docs:dev
```

访问地址通常为：`http://localhost:5173`

### 3. 构建打包

生成静态文件（默认输出到 `.vitepress/dist`）：

```bash
pnpm run docs:build
```

### 4. 本地预览构建产物

在构建完成后，可以预览生成的静态网站：

```bash
pnpm run docs:preview
```

## 部署

正式首页由 `index.md` 中的 `Home` 组件加载；下载入口为 `download.md`，英文路由保留在 `en/` 下。

官网与共享地图拼图算法变更时，GitHub Actions 的 `.github/workflows/official-site.yml` 会执行独立构建检查。部署产物为 `package/official-site/.vitepress/dist/`，将该目录作为静态站点根目录发布。

官网中的固定展示数据与素材来源见 `public/showcase/README.md`。演示站自动进入相册还需同步部署 `package/website` 前端，并由服务端启用演示模式。

# 官网 SEO 检索准确率优化说明

日期：2026-11-18
范围：`package/official-site`（VitePress 2.0 alpha），含本次 VanBlog 博客迁移（21 篇行影集相关文章迁入 `docs/blog/`）。

## 1. 诊断：检索准确率差在哪

「检索准确率」拆成四层：**发现 → 理解 → 归一 → 匹配**。迁移前官网的断点：

| 层 | 断点 | 后果 |
| --- | --- | --- |
| 发现 | `ai-docs.ts` 生成的 `sitemap.xml` / `llms.txt` / `llms-full.txt` / `ai-docs.json` 只覆盖 `guide`、`dev`，**博客完全不在索引内** | 搜索引擎与 AI 检索沿 sitemap/llms 索引找不到博客页 |
| 发现 | `sitemap.xml` 的 `lastmod` 全部等于构建当天 | 新鲜度信号失真，爬虫无法判断哪些页真的更新过 |
| 理解 | OG/Twitter 标签全站共用一组静态标题描述 | 分享卡片与部分检索摘要无法区分页面，主题信号被稀释 |
| 理解 | 无结构化数据（JSON-LD） | 无法进入文章类富结果，实体（作者/发布时间/站点）关系靠猜 |
| 归一 | 无 `rel=canonical` | 目录 URL 与 `.html` URL、博客原文与官网副本之间重复内容互相竞争 |
| 匹配 | 站内搜索默认分词把整段中文当一个 token | 「火车票」「以文搜图」这类子串查询命中率低 |

## 2. 本次已落地

1. **博客纳入全站索引基础设施**（`.vitepress/ai-docs.ts`）
   - 新增 `blog` 分类，`collectDocuments()` 扫描 `docs/blog` 与 `en/docs/blog`；
   - 博客页进入 `sitemap.xml`、`llms.txt`、`llms-full.txt`、`ai-docs.json`，并按站点约定镜像同路径 `.md`（AI 检索可直接读 Markdown 源）；
   - `lastmod` 改为读取 frontmatter 的 `updated` / `date`，无则回退构建日。
2. **逐页 canonical + OG/Twitter + 文章元数据 + JSON-LD**（`.vitepress/config.mts` 的 `transformPageData`）
   - 每页自指向 canonical（目录页用目录 URL，内容页用 `.html` URL，与 VitePress 实际路由一致）；
   - `og:title/description/url/image/type`、`twitter:*` 逐页注入；博客文章额外输出 `article:published_time` / `article:modified_time` 与 `BlogPosting` JSON-LD（headline、description、image、datePublished/Modified、author、publisher、mainEntityOfPage）；
   - 全局 head 只保留 `og:site_name`、`og:locale`、`twitter:card`，消除全站重复标签。
3. **内容层信号**（迁移产物 `docs/blog/*.md`）
   - frontmatter 补 `title / description / date / updated / author / image / source / keywords`；description 取自作者摘要（`<!-- more -->` 前）或首段，保证标题—描述—H1—正文主题一致；
   - 日期统一北京时间；空 alt 的图片用图注补齐 alt；
   - 文内 VanBlog 互链（`/post/<id>`）改写为官网博客链接，文末保留原文出处链接；索引页按主题分组并带日期，形成可抓取的内链枢纽；侧边栏同步分组。
4. **站内搜索中文匹配**（`config.mts` search options）
   - `processTerm` 在整词之外补充 CJK 二元组（索引与查询两侧一致），子串查询可命中；
   - `searchOptions: { fuzzy: 0.2, prefix: true }` + `detailedView: true` 提升容错与结果可核对性。
5. **图片外链治理**：按作者要求保留 VanBlog 原外链；相对路径补全为 `https://blog.siyuan.ink/...`；旧域名 `blog.lc044.love` 证书已失效，统一替换为主域名同路径（已验证 200）。

## 3. 为什么这些能提高检索准确率

- **信号叠加归一**：Google 官方说明 redirects > rel=canonical > sitemap 收录，且多种信号叠加更有效；自指向 canonical + sitemap 只收录规范 URL + 内链一律指向规范 URL，是官方推荐组合。参见 <https://developers.google.cn/search/docs/crawling-indexing/consolidate-duplicate-urls>。
- **重复内容处理**：同一文章存在于博客与官网两个域名时，必须明确谁是想排名的版本；转载/同步副本侧应回指 canonical（或在永久迁移时直接 301）。参见 <https://yoast.com/rel-canonical/>、<https://patrickstox.com/es/seo-t%C3%A9cnico/seo-para-news-y-discover/contenido-sindicado-y-seo/>。
- **主动提交缩短发现延迟**：百度普通收录 API 推送 + sitemap 提交可将新页收录从数周缩到数小时级；Bing/Yandex 等支持 IndexNow，一次提交共享给所有参与引擎。参见 <https://cloud.tencent.com/developer/article/2538468>、<https://blogs.bing.com/webmaster/2021/10/IndexNow-Instantly-Index-your-web-content-in-Search-Engines/>、<https://www.indexnow.org/faq>。
- **AI 检索入口**：`llms.txt` + 同路径 Markdown 镜像让 AI 搜索引擎拿到干净正文而非渲染 HTML，减少抽取噪声，提高引用准确率（本站已有该约定，本次把博客补齐）。

## 4. 待办（需要账号/服务器权限，未代做）

1. **博客侧归一（关键）**：官网副本已自指向 canonical，但博客原文若无信号，Google 可能仍选老博客 URL。三选一：
   - 永久迁移：博客服务器对已迁移的 `/post/<id>` 做 301 → `https://trailsnap.cn/docs/blog/<slug>`（最强信号）；
   - 保留博客阅读入口：nginx `sub_filter` 给这些文章页注入 `<link rel="canonical" href="官网URL">`；
   - 不处理：接受搜索引擎自行选择（不推荐，官网副本可能被当重复页过滤）。
   映射表见 `docs/blog/index.md` 与各文章 frontmatter `source`。
2. **百度**：搜索资源平台验证 `trailsnap.cn` → 普通收录提交 `https://trailsnap.cn/sitemap.xml`；开通 API 推送并把推送接入发布流程（`POST http://data.zz.baidu.com/urls?site=trailsnap.cn&token=<TOKEN>`，body 为每行一个 URL）。
3. **Google / Bing**：GSC 提交 sitemap 并对博客枢纽页与重点文章「请求编入索引」；Bing Webmaster 提交 sitemap，并部署 IndexNow key（根目录 `<key>.txt`）后在发布流程推送更新 URL。
4. **旧域名兜底**：`blog.lc044.love` 全站 301 到 `blog.siyuan.ink`，避免历史文章与外部引用中的旧图链/文链失效。
5. **hreflang（可选）**：guide/dev 已有中英双份，可补 `zh-CN` / `en` alternates；博客目前仅中文，en 索引页已做桥接，暂不需要。
6. **监控**：GSC「网页索引」报告 + 百度索引量；定期 `site:trailsnap.cn/docs/blog` 抽查收录与摘要是否取自逐页 description。

## 5. 验证方式

```powershell
pnpm --dir package/official-site run docs:build
# 产物检查（dist/）：
#   sitemap.xml 含 /docs/blog/*.html 且 lastmod 为文章日期
#   docs/blog/<slug>.html 含 rel=canonical、og:type=article、application/ld+json
#   llms.txt 含「博客」章节；docs/blog/<slug>.md 镜像存在
```

迁移边界：VanBlog「行影集」分类中 8 篇隐藏/私有旧文（留痕/微信工具时期）与 3 篇非行影集主题公开文（TraceBoard、EasyBox、微信图片加密）未迁移；`vibecoding 实录` 官网已有同源文章，仅补元数据不重复创建。
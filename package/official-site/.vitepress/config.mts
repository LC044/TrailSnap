import { defineConfig } from 'vitepress'
// import { withMermaid } from "vitepress-plugin-mermaid";
import {MermaidPlugin} from "@leelaa/vitepress-plugin-extended";
import { tabsMarkdownPlugin } from 'vitepress-plugin-tabs'
import { groupIconMdPlugin, groupIconVitePlugin } from 'vitepress-plugin-group-icons'

export default defineConfig({
  base: '/',
  markdown: {
    breaks: true,
    math: true,
    lineNumbers: true,
    image: {
      // 默认禁用；设置为 true 可为所有图片启用懒加载。
      lazyLoading: true
    },
    config: (md) => {
      // 使用更多的 Markdown-it 插件！
      MermaidPlugin(md)
      md.use(tabsMarkdownPlugin)
      md.use(groupIconMdPlugin)
    }
  },
  vite: { 
    plugins: [
      groupIconVitePlugin() //代码组图标
    ],
  },
  ignoreDeadLinks: [
    '/^http:\/\/localhost:\d+$/',
    'http://localhost:8082',
    // /^http:\/\/localhost:\d+$/ // 正则匹配所有 localhost:端口 形式的链接
  ],
  head: [
    ['link', { rel: 'icon', type: 'image/png', href: '/favicon.ico' }]
  ],

  locales: {
    root: {
      label: '简体中文',
      lang: 'zh-CN',
      title: "行影集",
      description: "AI 驱动的智能相册与旅行足迹记录工具",
      themeConfig: {
        nav: [
          { text: '首页', link: '/' },
          { text: 'CLI', link: '/cli' },
          { text: '用户指南', link: '/docs/guide/install' },
          { text: '开发者文档', link: '/docs/dev/guide' },
          { text: '博客', link: '/docs/blog/' },
          { text: '问题反馈', link: '/docs/guide/feedback' }
        ],
        sidebar: {
          '/docs/guide/': [
            { text: '概览', link: '/docs/guide/overview' },
            { text: '安装指南', link: '/docs/guide/install' },
            {
              text: 'Docker 部署',
              collapsed: true,
              items: [
                { text: '通用部署', link: '/docs/guide/docker/' },
                { text: 'Windows 部署', link: '/docs/guide/docker/windows' },
                { text: '绿联 NAS', link: '/docs/guide/docker/ugreen' },
                { text: '极空间', link: '/docs/guide/docker/zspace' },
                { text: '飞牛OS', link: '/docs/guide/docker/fnos' }
              ]
            },
            { text: '使用简介', link: '/docs/guide/user' },
            { text: '功能清单', link: '/docs/guide/features' },
            {
              text: '设置指南',
              link: '/docs/guide/settings/',
              collapsed: false,
              items: [
                { text: '地图设置', link: '/docs/guide/settings/mapsetting' },
                { text: '配置AI大模型', link: '/docs/guide/settings/aisetting' },
                { text: '添加外部图库', link: '/docs/guide/settings/directories' },
                { text: 'Token 设置', link: '/docs/guide/settings/tokensetting' },
              ]
            },
            {
              text: 'Agent Skills',
              link: '/docs/guide/agent/',
              collapsed: false,
              items: [
                { text: 'TrailSnap CLI 工具', link: '/docs/guide/agent/trailsnap-cli' },
                { text: 'Claude Code', link: '/docs/guide/agent/claudecode' },
                { text: 'OpenClaw', link: '/docs/guide/agent/openclaw' }
              ]
            },
            { text: '常见问题', link: '/docs/guide/questions' },
            { text: '问题反馈', link: '/docs/guide/feedback' },
            { text: '更新日志', link: '/docs/guide/changelog' },
          ],
          '/docs/dev/': [
              { text: '快速开始', link: '/docs/dev/guide' },
              {
                text: '设计文档',
                items: [
                  { text: '整体架构设计', link: '/docs/dev/architecture' },
                  { text: '前端设计', link: '/docs/dev/frontend' },
                  { text: '后端设计', link: '/docs/dev/backend' },
                  { text: 'AI微服务设计', link: '/docs/dev/ai_service' },
                  { text: '任务管理设计', link: '/docs/dev/task_manager' },
                  { text: '功能提案', link: '/docs/dev/feature-proposals' }
                ]
              },
              {
                text: 'AI提示词',
                collapsed: true,
                items: [
                  { text: '2025-12-25', link: '/docs/dev/prompt/2025-12-25' },
                  { text: '2026-01-07', link: '/docs/dev/prompt/2026-01-07' },
                  { text: '2026-01-24', link: '/docs/dev/prompt/2026-01-24' },
                  { text: '0.2.0', link: '/docs/dev/prompt/0.2.0' },
                  { text: '0.2.2', link: '/docs/dev/prompt/0.2.2' },
                  { text: '0.2.3', link: '/docs/dev/prompt/0.2.3' },
                  { text: '0.3.0', link: '/docs/dev/prompt/0.3.0' },
                  { text: '0.3.1', link: '/docs/dev/prompt/0.3.1' },
                  { text: '0.3.2', link: '/docs/dev/prompt/0.3.2' },
                  { text: '0.3.3', link: '/docs/dev/prompt/0.3.3' },
                  { text: '0.3.6', link: '/docs/dev/prompt/0.3.6' },
                  { text: '0.3.8', link: '/docs/dev/prompt/0.3.8' },
                  { text: '0.3.9', link: '/docs/dev/prompt/0.3.9' },
                  { text: '0.3.10', link: '/docs/dev/prompt/0.3.10' },
                  { text: '官网设计文档', link: '/docs/dev/prompt/official_website_design' }
                ]
              }
          ],
          '/docs/blog/': [
            {
              text: '博客',
              items: [
                { text: '文章列表', link: '/docs/blog/' },
                { text: '功能全景速览', link: '/docs/blog/feature-scan' },
              ]
            }
          ]
        },
        sidebarMenuLabel: '菜单',
        returnToTopLabel: '回到顶部',
        darkModeSwitchLabel: '主题',
        lightModeSwitchTitle: '切换到浅色模式',
        darkModeSwitchTitle: '切换到深色模式',
        docFooter: {
          prev: '上一页',
          next: '下一页'
        },
        outline: {
          label: '页面导航'
        },
        footer: {
          message: '基于 AGPL-3.0 许可发布',
          copyright: '版权所有 © 2025-至今 TrailSnap'
        }
      }
    },
    en: {
      label: 'English',
      lang: 'en-US',
      link: '/en/',
      title: "TrailSnap",
      description: "AI-powered Smart Album and Travel Footprint Recorder",
      themeConfig: {
        nav: [
          { text: 'Home', link: '/en/' },
          { text: 'CLI', link: '/en/cli' },
          { text: 'Demo', link: '/en/docs/guide/demo' },
          { text: 'Guide', link: '/en/docs/guide/install' },
          { text: 'Developers', link: '/en/docs/dev/guide' },
          { text: 'Blog', link: '/en/docs/blog/' },
          { text: 'Feedback', link: '/en/docs/guide/feedback' }
        ],
        sidebar: {
          '/en/docs/guide/': [
            {
              text: 'User Guide',
              items: [
                { text: 'Overview', link: '/en/docs/guide/overview' },
                { text: 'Installation', link: '/en/docs/guide/install' },
                {
                  text: 'Docker Deployment',
                  collapsed: true,
                  items: [
                    { text: 'Generic', link: '/en/docs/guide/docker/' },
                    { text: 'Windows', link: '/en/docs/guide/docker/windows' },
                    { text: 'Ugreen NAS', link: '/en/docs/guide/docker/ugreen' },
                    { text: 'Zspace', link: '/en/docs/guide/docker/zspace' },
                    { text: 'Fnos', link: '/en/docs/guide/docker/fnos' }
                  ]
                },
                { text: 'User Manual', link: '/en/docs/guide/user' },
                {
                  text: 'Settings',
                  link: '/en/docs/guide/settings/',
                  collapsed: true,
                  items: [
                    { text: 'Map Settings', link: '/en/docs/guide/settings/mapsetting' },
                    { text: 'AI Settings', link: '/en/docs/guide/settings/aisetting' },
                    { text: 'Directories', link: '/en/docs/guide/settings/directories' },
                    { text: 'Token Settings', link: '/en/docs/guide/settings/tokensetting' }
                  ]
                },
                {
                  text: 'Agent Skills',
                  link: '/en/docs/guide/agent/',
                  collapsed: false,
                  items: [
                    { text: 'TrailSnap CLI', link: '/en/docs/guide/agent/trailsnap-cli' },
                    { text: 'Claude Code', link: '/en/docs/guide/agent/claudecode' },
                    { text: 'OpenClaw', link: '/en/docs/guide/agent/openclaw' }
                  ]
                },
                { text: 'Questions', link: '/en/docs/guide/questions' },
                { text: 'Feedback', link: '/en/docs/guide/feedback' },
                { text: 'Changelog', link: '/en/docs/guide/changelog' },
              ]
            }
          ],
          '/en/docs/dev/': [
            {
              text: 'Developer Guide',
              items: [
                { text: 'Quick Start', link: '/en/docs/dev/guide' },
                { text: 'Architecture', link: '/en/docs/dev/architecture' },
                { text: 'Frontend', link: '/en/docs/dev/frontend' },
                { text: 'Backend', link: '/en/docs/dev/backend' },
                { text: 'AI Service', link: '/en/docs/dev/ai_service' },
                { text: 'Task Manager', link: '/en/docs/dev/task_manager' },
                { text: 'Feature Proposals', link: '/en/docs/dev/feature-proposals' },
                {
                  text: 'AI Prompts',
                  link: '/en/docs/dev/prompt',
                  collapsed: false,
                  items: [
                    { text: '2025-12-25', link: '/en/docs/dev/prompt/2025-12-25' },
                    { text: '2026-01-07', link: '/en/docs/dev/prompt/2026-01-07' },
                    { text: '2026-01-24', link: '/en/docs/dev/prompt/2026-01-24' },
                    { text: 'Official Website Design', link: '/en/docs/dev/prompt/official_website_design' }
                  ]
                }
              ]
            }
          ],
          '/en/docs/blog/': [
            {
              text: 'Blog',
              items: [
                { text: 'Articles', link: '/en/docs/blog/' },
                { text: 'Feature Scan', link: '/en/docs/blog/feature-scan' },
              ]
            }
          ]
        },
        sidebarMenuLabel: 'Menu',
        returnToTopLabel: 'Return to top',
        darkModeSwitchLabel: 'Theme',
        lightModeSwitchTitle: 'Switch to light mode',
        darkModeSwitchTitle: 'Switch to dark mode',
        docFooter: {
          prev: 'Previous',
          next: 'Next'
        },
        footer: {
          message: 'Released under the AGPL-3.0 License',
          copyright: 'Copyright © 2025-present TrailSnap'
        }
      }
    }
  },

  themeConfig: {
    socialLinks: [
      { icon: 'github', link: 'https://github.com/LC044/TrailSnap' }
    ],

    outline: {
      label: 'On this page'
    },

    search: {
      provider: 'local',
      options: {
        locales: {
          root: {
            translations: {
              button: {
                buttonText: '搜索',
                buttonAriaLabel: '搜索'
              },
              modal: {
                noResultsText: '没有找到相关结果',
                resetButtonTitle: '重置搜索',
                footer: {
                  selectText: '选择',
                  navigateText: '导航',
                  closeText: '关闭'
                }
              }
            }
          },
          en: {
            translations: {
              button: {
                buttonText: 'Search',
                buttonAriaLabel: 'Search'
              },
              modal: {
                noResultsText: 'No results found',
                resetButtonTitle: 'Reset search',
                footer: {
                  selectText: 'to select',
                  navigateText: 'to navigate',
                  closeText: 'to close'
                }
              }
            }
          }
        }
      }
    }
  }
})

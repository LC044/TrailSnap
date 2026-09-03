import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Plugin } from 'vite'

type Language = 'zh-CN' | 'en'

interface AiDocument {
  title: string
  description: string
  categoryKey: string
  category: string
  language: Language
  htmlPath: string
  markdownPath: string
  content: string
  sourcePath: string
  emitMarkdown: boolean
}

const siteUrl = 'https://trailsnap.cn'
const currentDir = path.dirname(fileURLToPath(import.meta.url))
const siteRoot = path.resolve(currentDir, '..')
const today = new Date().toISOString().slice(0, 10)

const categoryLabels: Record<string, Record<Language, string>> = {
  'ai-access': { 'zh-CN': 'AI Agent 文档入口', en: 'AI Agent access' },
  'getting-started': { 'zh-CN': '快速开始', en: 'Getting started' },
  installation: { 'zh-CN': '安装部署', en: 'Installation' },
  docker: { 'zh-CN': 'Docker 部署', en: 'Docker deployment' },
  settings: { 'zh-CN': '设置指南', en: 'Settings' },
  usage: { 'zh-CN': '使用指南', en: 'User guide' },
  reference: { 'zh-CN': '参考信息', en: 'Reference' },
  agent: { 'zh-CN': 'Agent 集成', en: 'Agent integration' },
  developer: { 'zh-CN': '开发者文档', en: 'Developer documentation' },
}

const categoryOrder = [
  'ai-access',
  'getting-started',
  'installation',
  'docker',
  'settings',
  'usage',
  'reference',
  'agent',
  'developer',
]

function walkMarkdownFiles(dir: string): string[] {
  if (!fs.existsSync(dir)) return []

  const files: string[] = []

  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      files.push(...walkMarkdownFiles(fullPath))
    } else if (entry.isFile() && entry.name.toLowerCase().endsWith('.md')) {
      files.push(fullPath)
    }
  }

  return files.sort((a, b) => a.localeCompare(b, 'en'))
}

function stripFrontmatter(content: string): string {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(content)
  return match ? content.slice(match[0].length) : content
}

function frontmatterValue(content: string, key: string): string | undefined {
  const match = new RegExp(`^${key}:\\s*(.+)$`, 'm').exec(content)
  return match?.[1]?.trim().replace(/^['"]|['"]$/g, '')
}

function cleanInlineText(text: string): string {
  return text
    .replace(/<[^>]+>/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^[-*+]\s+/, '')
    .replace(/[*_`]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function extractTitle(content: string, sourcePath: string, language: Language): string {
  const frontmatterTitle = frontmatterValue(content, 'title')
  if (frontmatterTitle) return cleanInlineText(frontmatterTitle)

  let inFence = false
  for (const line of stripFrontmatter(content).split(/\r?\n/)) {
    if (line.trimStart().startsWith('```')) inFence = !inFence
    if (inFence) continue

    const heading = /^#\s+(.+)$/.exec(line)
    if (heading) return cleanInlineText(heading[1])
  }

  const basename = path.basename(sourcePath, '.md')
  if (basename === 'overview') return language === 'zh-CN' ? '概览' : 'Overview'
  if (basename === 'windows') return language === 'zh-CN' ? 'Windows 部署' : 'Windows Deployment'
  return basename
    .split(/[-_]/)
    .map((part) => (part ? part.charAt(0).toUpperCase() + part.slice(1) : part))
    .join(' ')
}

function extractDescription(content: string): string {
  const frontmatterDescription = frontmatterValue(content, 'description')
  if (frontmatterDescription) return cleanInlineText(frontmatterDescription)

  let inFence = false
  for (const line of stripFrontmatter(content).split(/\r?\n/)) {
    const trimmed = line.trim()
    if (trimmed.startsWith('```')) inFence = !inFence
    if (inFence) continue
    if (!trimmed || trimmed.startsWith('#') || trimmed.startsWith('|') || trimmed.startsWith('!') || trimmed.startsWith('<') || trimmed.startsWith('>') || trimmed.startsWith(':::')) continue

    const text = cleanInlineText(trimmed)
    if (!text) continue
    return text.length > 220 ? `${text.slice(0, 217)}...` : text
  }

  return 'TrailSnap official documentation.'
}

function categoryForPath(relativePath: string): string {
  const normalized = relativePath.replace(/\\/g, '/')
  if (normalized === 'public/install.md') return 'agent'
  if (normalized.includes('/guide/ai-access.md')) return 'ai-access'
  if (normalized.includes('/guide/agent/')) return 'agent'
  if (normalized.includes('/guide/docker/')) return 'docker'
  if (normalized.includes('/guide/settings/')) return 'settings'
  if (/\/guide\/(overview|preflight|install|desktop-ai-extension|mobile-app)\.md$/.test(normalized)) return 'installation'
  if (/\/guide\/(user|features)\.md$/.test(normalized)) return 'usage'
  if (normalized.includes('/guide/')) return 'reference'
  return 'developer'
}

function routesFromMarkdownPath(markdownPath: string): { htmlPath: string; markdownPath: string } {
  const normalized = markdownPath.replace(/\\/g, '/')
  if (normalized.endsWith('/index.md')) {
    return { htmlPath: normalized.slice(0, -'index.md'.length), markdownPath: normalized }
  }
  return { htmlPath: `${normalized.slice(0, -'.md'.length)}.html`, markdownPath: normalized }
}

function createDocument(sourcePath: string, markdownPath: string, language: Language, emitMarkdown: boolean): AiDocument {
  const content = fs.readFileSync(sourcePath, 'utf8')
  const relativePath = path.relative(siteRoot, sourcePath)
  const categoryKey = categoryForPath(relativePath)

  return {
    title: extractTitle(content, sourcePath, language),
    description: extractDescription(content),
    categoryKey,
    category: categoryLabels[categoryKey]?.[language] ?? 'Documentation',
    language,
    ...routesFromMarkdownPath(markdownPath),
    content,
    sourcePath: relativePath.replace(/\\/g, '/'),
    emitMarkdown,
  }
}

function collectDocuments(): AiDocument[] {
  const documents: AiDocument[] = []

  for (const language of ['zh-CN', 'en'] as Language[]) {
    const localeDirectory = language === 'zh-CN' ? path.join(siteRoot, 'docs') : path.join(siteRoot, 'en', 'docs')
    const markdownPrefix = language === 'zh-CN' ? '/docs' : '/en/docs'

    for (const section of ['guide', 'dev']) {
      for (const file of walkMarkdownFiles(path.join(localeDirectory, section))) {
        const relativeToLocale = path.relative(localeDirectory, file)
        if (relativeToLocale.replace(/\\/g, '/').startsWith('dev/prompt/')) continue
        const markdownPath = `${markdownPrefix}/${relativeToLocale.replace(/\\/g, '/')}`
        documents.push(createDocument(file, markdownPath, language, true))
      }
    }
  }

  const cliInstallDoc = path.join(siteRoot, 'public', 'install.md')
  if (fs.existsSync(cliInstallDoc)) {
    documents.push(createDocument(cliInstallDoc, '/install.md', 'zh-CN', false))
  }

  const categoryRank = new Map(categoryOrder.map((key, index) => [key, index]))
  return documents.sort((a, b) => {
    const categoryDifference = (categoryRank.get(a.categoryKey) ?? 999) - (categoryRank.get(b.categoryKey) ?? 999)
    if (categoryDifference !== 0) return categoryDifference
    if (a.language !== b.language) return a.language === 'zh-CN' ? -1 : 1
    return a.markdownPath.localeCompare(b.markdownPath, 'en')
  })
}

function llmsIndex(documents: AiDocument[]): string {
  const lines: string[] = [
    '# TrailSnap 行影集 documentation',
    '',
    `> AI-powered, self-hosted photo library. This index is optimized for AI agents and links directly to Markdown source.`,
    '',
    '## AI-friendly entry points',
    '',
    `- Full documentation: ${siteUrl}/llms-full.txt`,
    `- Structured index: ${siteUrl}/ai-docs.json`,
    `- CLI installation prompt: ${siteUrl}/install.md`,
    '',
  ]

  for (const language of ['zh-CN', 'en'] as Language[]) {
    const languageDocuments = documents.filter((document) => document.language === language)
    if (languageDocuments.length === 0) continue

    lines.push(`## ${language === 'zh-CN' ? '中文文档' : 'English documentation'}`)

    let currentCategory = ''
    for (const document of languageDocuments) {
      if (document.category !== currentCategory) {
        currentCategory = document.category
        lines.push('', `### ${currentCategory}`)
      }
      lines.push(`- [${document.title}](${siteUrl}${document.markdownPath}): ${document.description}`)
    }

    lines.push('')
  }

  return `${lines.join('\n').trimEnd()}\n`
}

function llmsFullText(documents: AiDocument[]): string {
  const chunks = documents.map((document) => [
    `# ${document.title}`,
    '',
    `- Source: ${siteUrl}${document.htmlPath}`,
    `- Markdown: ${siteUrl}${document.markdownPath}`,
    `- Category: ${document.category}`,
    `- Language: ${document.language}`,
    '',
    stripFrontmatter(document.content).trimEnd(),
  ].join('\n'))

  return [
    '# TrailSnap documentation for AI agents',
    '',
    `This file combines the official TrailSnap user guide, deployment guide, agent guide, and core developer documentation. Updated: ${today}.`,
    '',
    chunks.join('\n\n---\n\n\n'),
    '',
  ].join('\n')
}

function aiDocsJson(documents: AiDocument[]): string {
  return `${JSON.stringify(
    {
      name: 'TrailSnap',
      description: 'AI-powered, self-hosted photo library and travel footprint application.',
      site: siteUrl,
      updated: today,
      conventions: {
        markdownRule: 'Documentation HTML pages are mirrored as Markdown at the same path with .md instead of .html.',
        recommendedEntry: '/llms.txt',
      },
      documents: documents.map((document) => ({
        title: document.title,
        description: document.description,
        category: document.category,
        language: document.language,
        url: `${siteUrl}${document.htmlPath}`,
        markdown: `${siteUrl}${document.markdownPath}`,
        source: document.sourcePath,
      })),
    },
    null,
    2,
  )}\n`
}

function sitemap(documents: AiDocument[]): string {
  const urls = [
    { path: '/', priority: '1.0' },
    { path: '/download', priority: '0.9' },
    { path: '/cli', priority: '0.8' },
    { path: '/install.md', priority: '0.8' },
    ...documents.map((document) => ({
      path: document.htmlPath,
      priority: document.categoryKey === 'agent' ? '0.9' : '0.7',
    })),
  ]

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ...urls.map((url) => [
      '  <url>',
      `    <loc>${siteUrl}${url.path}</loc>`,
      `    <lastmod>${today}</lastmod>`,
      `    <priority>${url.priority}</priority>`,
      '  </url>',
    ].join('\n')),
    '</urlset>',
    '',
  ].join('\n')
}

const robots = [
  'User-agent: *',
  'Allow: /',
  'Disallow: /docs/dev/prompt/',
  'Disallow: /en/docs/dev/prompt/',
  '',
  `Sitemap: ${siteUrl}/sitemap.xml`,
  '',
].join('\n')

export function aiDocsPlugin(): Plugin {
  let isServerBuild = false

  return {
    name: 'trailsnap-ai-docs',
    apply: 'build',
    configResolved(config) {
      isServerBuild = Boolean(config.build.ssr)
    },
    generateBundle() {
      if (isServerBuild) return

      const documents = collectDocuments()

      const outputs = new Map<string, string>([
        ['llms.txt', llmsIndex(documents)],
        ['llms-full.txt', llmsFullText(documents)],
        ['ai-docs.json', aiDocsJson(documents)],
        ['robots.txt', robots],
        ['sitemap.xml', sitemap(documents)],
      ])

      for (const document of documents) {
        if (!document.emitMarkdown) continue
        outputs.set(document.markdownPath.replace(/^\//, ''), document.content)
      }

      for (const [fileName, source] of outputs) {
        this.emitFile({ type: 'asset', fileName, source })
      }
    },
  }
}

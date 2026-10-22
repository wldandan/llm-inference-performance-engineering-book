import { defineConfig } from 'vitepress'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const contentDir = fileURLToPath(new URL('../content', import.meta.url))

// 取每篇正文第一个一级标题作为侧边栏文案
function pageTitle(relPath: string): string {
  const src = readFileSync(join(contentDir, relPath), 'utf-8')
  const m = src.match(/^#\s+(.+?)\s*$/m)
  return m ? m[1] : relPath
}

// 侧边栏用短标题：去掉英文括注，去掉"："之后的副标题
function short(title: string): string {
  return title.replace(/（[^）]*）/g, '').split('：')[0].trim()
}

const partGroups = [
  { part: 'part01', chapters: ['ch01', 'ch02', 'ch03', 'ch04', 'ch05'] },
  { part: 'part02', chapters: ['ch06', 'ch07', 'ch08', 'ch09', 'ch10'] },
  { part: 'part03', chapters: ['ch11', 'ch12', 'ch13', 'ch14'] },
  { part: 'part04', chapters: ['ch15', 'ch16', 'ch17', 'ch18', 'ch19'] },
  { part: 'part05', chapters: ['ch20', 'ch21', 'ch22', 'ch23', 'ch24', 'ch25'] },
  { part: 'part06', chapters: ['ch26', 'ch27', 'ch28', 'ch29'] },
  { part: 'part07', chapters: ['ch30'] },
]

const chapterItem = (ch: string) => ({
  text: short(pageTitle(`${ch}/${ch}.md`)),
  link: `/${ch}/${ch}`,
})

const appendixItem = (dir: string, file: string) => ({
  text: short(pageTitle(`advanced/${dir}/${file}`)),
  link: `/advanced/${dir}/${file.replace(/\.md$/, '')}`,
})

export default defineConfig({
  lang: 'zh-CN',
  title: 'LLM 推理性能工程实战',
  description: '从模型原理、性能分析到 Serving 与 Agent 优化',
  srcDir: 'content',
  base: '/llm-inference-performance-handbook/',
  // 120 个插图注记文件不生成页面、不进搜索索引
  srcExclude: ['**/figures/*.md'],
  lastUpdated: true,
  // 正文里有指向 ../../code/ 的仓库内链接，不在站点内，跳过死链检查
  ignoreDeadLinks: [(url: string) => url.includes('/code/')],

  head: [
    ['link', { rel: 'preconnect', href: 'https://fonts.googleapis.com' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' }],
    ['link', {
      rel: 'stylesheet',
      href: 'https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap',
    }],
  ],

  themeConfig: {
    siteTitle: 'LLM 推理性能工程实战',
    nav: [
      { text: '开始阅读', link: '/preface' },
      { text: '配套代码', link: 'https://github.com/wldandan/llm-inference-performance-handbook/tree/main/code' },
      {
        text: '速查',
        items: [
          { text: '附录 F · 公式、前提与失效点', link: '/reference/appendix-f' },
          { text: '术语表', link: '/reference/glossary' },
          { text: '实验环境与版本', link: '/reference/environment' },
        ],
      },
    ],
    sidebar: [
      { text: pageTitle('preface.md'), link: '/preface' },
      { text: short(pageTitle('ch00/ch00.md')), link: '/ch00/ch00' },
      ...partGroups.map(({ part, chapters }) => ({
        text: short(pageTitle(`${part}.md`)),
        collapsed: true,
        items: [
          { text: '本篇导读', link: `/${part}` },
          ...chapters.map(chapterItem),
        ],
      })),
      {
        text: '附录',
        collapsed: true,
        items: [
          { text: '进阶附录总览', link: '/advanced/README' },
          appendixItem('appendix-a-gpu-architecture', 'appendix-a.md'),
          appendixItem('appendix-b-cuda-kernel', 'appendix-b.md'),
          appendixItem('appendix-c-multi-gpu', 'appendix-c.md'),
          appendixItem('appendix-d-moe', 'appendix-d.md'),
          appendixItem('appendix-e-pd-disaggregation', 'appendix-e.md'),
          { text: short(pageTitle('reference/appendix-f.md')), link: '/reference/appendix-f' },
          { text: pageTitle('reference/glossary.md'), link: '/reference/glossary' },
          { text: pageTitle('reference/environment.md'), link: '/reference/environment' },
        ],
      },
    ],
    outline: { level: [2, 3], label: '本页目录' },
    docFooter: { prev: '上一篇', next: '下一篇' },
    lastUpdated: { text: '最近更新' },
    editLink: {
      pattern: 'https://github.com/wldandan/llm-inference-performance-handbook/edit/main/content/:path',
      text: '在 GitHub 上编辑此页',
    },
    search: {
      provider: 'local',
      options: {
        locales: {
          root: {
            translations: {
              button: { buttonText: '搜索', buttonAriaLabel: '搜索' },
              modal: {
                displayDetails: '显示详细列表',
                resetButtonTitle: '重置搜索',
                backButtonTitle: '关闭搜索',
                noResultsText: '没有相关结果',
                footer: {
                  selectText: '选择',
                  selectKeyAriaLabel: '回车',
                  navigateText: '切换',
                  navigateUpKeyAriaLabel: '上箭头',
                  navigateDownKeyAriaLabel: '下箭头',
                  closeText: '关闭',
                  closeKeyAriaLabel: 'esc',
                },
              },
            },
          },
        },
      },
    },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/wldandan/llm-inference-performance-handbook' },
    ],
    darkModeSwitchLabel: '外观',
    sidebarMenuLabel: '目录',
    returnToTopLabel: '回到顶部',
  },
})

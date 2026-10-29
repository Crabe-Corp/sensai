import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { BASE, REPO_BRANCH, REPO_URL, SITE } from './site.config.mjs';

const mermaid = `
const blocks = document.querySelectorAll('pre.mermaid');
if (blocks.length) {
  const { default: mermaid } = await import('https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs');
  mermaid.initialize({ startOnLoad: false, theme: 'neutral', fontFamily: 'inherit' });
  await mermaid.run({ nodes: blocks });
}`;

export default defineConfig({
  site: SITE,
  base: BASE,
  trailingSlash: 'always',
  integrations: [
    starlight({
      title: 'SensAI',
      description: 'Assistant IA modulaire & agentique inspiré des 7 Royaumes Combattants.',
      logo: { src: './src/assets/logo.svg', alt: 'SensAI Logo' },
      favicon: '/favicon.svg',
      social: { github: REPO_URL },
      editLink: { baseUrl: `${REPO_URL}/edit/${REPO_BRANCH}/website/` },
      customCss: ['./src/styles/theme.css'],
      head: [{ tag: 'script', attrs: { type: 'module' }, content: mermaid }],
      expressiveCode: { themes: ['github-dark-dimmed', 'github-light'] },
      sidebar: [
        {
          label: 'Présentation',
          items: [
            { label: 'Introduction & Vision', slug: 'overview' },
            { label: 'Architecture Globale', slug: 'architecture' },
          ],
        },
        {
          label: 'Interfaces',
          items: [
            { label: 'Guide du CLI', slug: 'interfaces/cli' },
            { label: 'Présentation du Frontend', slug: 'interfaces/frontend' },
            { label: 'Architecture & Protocoles Frontend', slug: 'interfaces/frontend-architecture' },
          ],
        },
        {
          label: 'Moteur & Intelligence',
          items: [
            { label: 'Système d\'Outils & MCP', slug: 'features/tools' },
            { label: 'RAG & Cache Sémantique', slug: 'features/rag-and-cache' },
          ],
        },
        {
          label: 'Projet & Équipe',
          items: [
            { label: 'Guide du Contributeur', slug: 'project/contributing' },
          ],
        },
      ],
    }),
  ],
});

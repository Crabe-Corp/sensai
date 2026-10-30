import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { BASE, REPO_BRANCH, REPO_URL, SITE } from './site.config.mjs';

const mermaidScript = `
function setupMermaidZoom() {
  let modal = document.getElementById('mermaid-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'mermaid-modal';
    modal.innerHTML = \`
      <div class="mermaid-modal-backdrop"></div>
      <div class="mermaid-modal-content">
        <div class="mermaid-modal-svg"></div>
        <button class="mermaid-modal-close" type="button" aria-label="Fermer">✕</button>
      </div>
    \`;
    document.body.appendChild(modal);

    const closeModal = () => modal.classList.remove('active');
    modal.querySelector('.mermaid-modal-backdrop').addEventListener('click', closeModal);
    modal.querySelector('.mermaid-modal-close').addEventListener('click', closeModal);
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeModal();
    });
  }

  document.querySelectorAll('pre.mermaid').forEach((block) => {
    if (block.dataset.zoomAttached) return;
    block.dataset.zoomAttached = 'true';
    block.addEventListener('click', () => {
      const svg = block.querySelector('svg');
      if (!svg) return;
      const target = modal.querySelector('.mermaid-modal-svg');
      target.innerHTML = svg.outerHTML;
      modal.classList.add('active');
    });
  });
}

async function renderMermaid() {
  const blocks = document.querySelectorAll('pre.mermaid:not([data-processed="true"])');
  if (blocks.length) {
    let m = window.mermaid;
    if (!m) {
      try {
        const mod = await import('https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs');
        m = mod.default;
      } catch (e) {
        console.error('Could not load Mermaid from CDN:', e);
      }
    }
    if (m) {
      m.initialize({
        startOnLoad: false,
        theme: 'dark',
        themeVariables: {
          darkTheme: true,
          background: '#121316',
          primaryColor: '#1e293b',
          primaryTextColor: '#f8fafc',
          primaryBorderColor: '#3b82f6',
          lineColor: '#64748b',
          secondaryColor: '#1e293b',
          tertiaryColor: '#09090b'
        },
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
      });
      try {
        await m.run({ nodes: Array.from(blocks) });
        setupMermaidZoom();
      } catch (err) {
        console.error('Mermaid render error:', err);
      }
    }
  } else {
    setupMermaidZoom();
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', renderMermaid);
} else {
  renderMermaid();
}
document.addEventListener('astro:page-load', renderMermaid);
`;

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
      defaultLocale: 'fr',
      locales: {
        fr: {
          label: 'Français',
          lang: 'fr',
        },
        en: {
          label: 'English',
          lang: 'en',
        },
      },
      social: { github: REPO_URL },
      editLink: { baseUrl: `${REPO_URL}/edit/${REPO_BRANCH}/website/` },
      customCss: ['./src/styles/theme.css'],
      head: [
        { tag: 'script', attrs: { src: `${BASE}/mermaid.min.js` } },
        { tag: 'script', attrs: { type: 'module' }, content: mermaidScript },
      ],
      expressiveCode: { themes: ['github-dark-dimmed', 'github-light'] },
      sidebar: [
        {
          label: 'Présentation',
          translations: { en: 'Overview' },
          items: [
            { label: 'Introduction & Vision', slug: 'overview', translations: { en: 'Introduction & Vision' } },
            { label: 'Architecture Globale', slug: 'architecture', translations: { en: 'Global Architecture' } },
          ],
        },
        {
          label: 'Interfaces',
          translations: { en: 'Interfaces' },
          items: [
            { label: 'Guide du CLI', slug: 'interfaces/cli', translations: { en: 'CLI Guide' } },
            { label: 'Présentation du Frontend', slug: 'interfaces/frontend', translations: { en: 'Frontend Overview' } },
            { label: 'Architecture & Protocoles Frontend', slug: 'interfaces/frontend-architecture', translations: { en: 'Frontend Architecture & Protocols' } },
          ],
        },
        {
          label: 'Moteur & Intelligence',
          translations: { en: 'Engine & Intelligence' },
          items: [
            { label: 'Système d\'Outils & MCP', slug: 'features/tools', translations: { en: 'Tools System & MCP' } },
            { label: 'RAG & Cache Sémantique', slug: 'features/rag-and-cache', translations: { en: 'RAG & Semantic Cache' } },
          ],
        },
        {
          label: 'Projet & Équipe',
          translations: { en: 'Project & Team' },
          items: [
            { label: 'Guide du Contributeur', slug: 'project/contributing', translations: { en: 'Contributor Guide' } },
          ],
        },
      ],
    }),
  ],
});

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { BASE, REPO_BRANCH, REPO_URL } from '../site.config.mjs';

const websiteDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(process.env.SENSAI_REPO_ROOT ?? path.join(websiteDir, '..'));
const contentDir = path.join(websiteDir, 'src', 'content', 'docs');

const PAGES = [
  {
    slug: 'overview',
    src: 'README.md',
    title: { fr: "Vue d'ensemble & Vision", en: 'Overview & Vision' },
    description: { fr: 'Introduction générale au projet SensAI, ses objectifs et ses composants.', en: 'General overview of the SensAI project, its objectives and architecture.' },
    order: 1,
  },
  {
    slug: 'architecture',
    src: 'README.md',
    title: { fr: 'Architecture Globale', en: 'Global Architecture' },
    description: { fr: 'Architecture des systèmes SensAI, flux de données et composants.', en: 'SensAI system architecture, data flows and core components.' },
    order: 2,
  },
  {
    slug: 'interfaces/cli',
    src: 'cli.md',
    title: { fr: 'Guide du CLI SensAI', en: 'SensAI CLI Guide' },
    description: { fr: 'Commandes, options, modes /encyclopedia et /simulation.', en: 'Commands, options, /encyclopedia and /simulation modes.' },
    order: 1,
  },
  {
    slug: 'interfaces/frontend',
    src: 'frontend.md',
    title: { fr: 'SensAI Web Frontend', en: 'SensAI Web Frontend' },
    description: { fr: 'Interface web React 19, Tailwind v4, shadcn/ui et design Dark Obsidian.', en: 'React 19 web interface, Tailwind v4, shadcn/ui and Dark Obsidian design.' },
    order: 2,
  },
  {
    slug: 'interfaces/frontend-architecture',
    src: 'frontend-architecture.md',
    title: { fr: 'Architecture & Protocoles Frontend', en: 'Frontend Architecture & Protocols' },
    description: { fr: 'Streaming NDJSON, formulaires ask_user_form, Human-in-the-loop et budget de tokens.', en: 'NDJSON streaming, ask_user_form, Human-in-the-loop and token budget.' },
    order: 3,
  },
  {
    slug: 'features/tools',
    src: 'tools-guide.md',
    title: { fr: "Système d'Outils & MCP", en: 'Tools System & MCP' },
    description: { fr: "Création d'outils avec @tool, registre dynamique et serveurs MCP.", en: 'Tool development with @tool, dynamic registry and MCP servers.' },
    order: 1,
  },
  {
    slug: 'features/rag-and-cache',
    src: 'rag-and-cache.md',
    title: { fr: 'RAG & Cache Sémantique', en: 'RAG & Semantic Cache' },
    description: { fr: 'Vectorisation Qdrant des manuscrits historiques et cache sémantique à deux niveaux.', en: 'Qdrant vectorization of historical chronicles and two-tier semantic cache.' },
    order: 2,
  },
  {
    slug: 'project/contributing',
    src: 'contributing.md',
    title: { fr: 'Guide du Contributeur', en: 'Contributor Guide' },
    description: { fr: 'Conventions de code, contributeurs, standards de test et cycle de vie des PRs.', en: 'Code conventions, team contributors, testing standards and PR lifecycle.' },
    order: 1,
  },
];

function convertMermaid(text) {
  return text.replace(/^```mermaid\r?\n([\s\S]*?)^```$/gm, (all, graph) => {
    const unlisted = graph.replace(/"(\d+)\. /g, '"\u200b$1. ');
    const escaped = unlisted.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return `<pre class="mermaid">\n${escaped}</pre>`;
  });
}

function cleanMarkdown(content) {
  const withoutH1 = content.replace(/^#\s+[^\n]+\n+/, '');
  return convertMermaid(withoutH1);
}

function readDoc(lang, rel) {
  const file = path.join(repoRoot, 'docs', lang, rel);
  if (!fs.existsSync(file)) return null;
  return fs.readFileSync(file, 'utf8');
}

function frontmatter(title, desc, src, order) {
  const lines = ['---'];
  lines.push(`title: ${JSON.stringify(title)}`);
  if (desc) lines.push(`description: ${JSON.stringify(desc)}`);
  if (src) lines.push(`editUrl: ${JSON.stringify(`${REPO_URL}/edit/${REPO_BRANCH}/${src}`)}`);
  lines.push('sidebar:');
  lines.push(`  order: ${order}`);
  lines.push('---', '');
  return lines.join('\n');
}

function sync() {
  fs.rmSync(contentDir, { recursive: true, force: true });
  fs.mkdirSync(contentDir, { recursive: true });

  // French landing page
  const frLanding = [
    '---',
    'title: SensAI',
    'description: Assistant IA modulaire et agentique inspiré des 7 Royaumes Combattants de la Chine antique.',
    'template: splash',
    'editUrl: false',
    'hero:',
    '  title: SensAI',
    '  tagline: Assistant IA modulaire, agentique et souverain. Explorez le lore historique des 7 Royaumes Combattants ou lancez des simulations de guerre tactiques.',
    '  image:',
    '    file: ../../../assets/logo.svg',
    '  actions:',
    `    - text: Découvrir le projet`,
    `      link: ${BASE}/fr/overview/`,
    '      icon: right-arrow',
    `    - text: Guide du CLI`,
    `      link: ${BASE}/fr/interfaces/cli/`,
    '      icon: laptop',
    '      variant: secondary',
    `    - text: Interface Frontend`,
    `      link: ${BASE}/fr/interfaces/frontend/`,
    '      icon: document',
    '      variant: minimal',
    `    - text: GitHub`,
    `      link: ${REPO_URL}`,
    '      icon: external',
    '      variant: minimal',
    '---',
    '',
    '## Deux interfaces, un moteur souverain',
    '',
    'SensAI combine deux interfaces complémentaires développées pour explorer l\'histoire des Sept Royaumes Combattants de la Chine antique :',
    '',
    '- **SensAI CLI** : Le terminal de référence pour le rôle immersif, l\'enrichissement RAG automatique dans les chroniques antiques (*Shiji*, *Zhan Guo Ce*) et la simulation de batailles tactiques au tour par tour (`/simulation [seed]`).',
    '- **SensAI Web Frontend** : Cockpit graphique moderne en React 19 et shadcn/ui, offrant le streaming SSE temps-réel, les formulaires interactifs (`sensai-form`), la validation sécurisée des actions sensibles (*Human-in-the-loop*) et le suivi en direct du budget de tokens.',
  ].join('\n');

  // English landing page
  const enLanding = [
    '---',
    'title: SensAI',
    'description: Modular, agentic AI assistant inspired by the 7 Warring States of Ancient China.',
    'template: splash',
    'editUrl: false',
    'hero:',
    '  title: SensAI',
    '  tagline: Modular, sovereign and agentic AI assistant. Explore ancient historical chronicles or launch turn-based tactical war simulations.',
    '  image:',
    '    file: ../../../assets/logo.svg',
    '  actions:',
    `    - text: Explore the Project`,
    `      link: ${BASE}/en/overview/`,
    '      icon: right-arrow',
    `    - text: CLI Guide`,
    `      link: ${BASE}/en/interfaces/cli/`,
    '      icon: laptop',
    '      variant: secondary',
    `    - text: Web Frontend`,
    `      link: ${BASE}/en/interfaces/frontend/`,
    '      icon: document',
    '      variant: minimal',
    `    - text: GitHub`,
    `      link: ${REPO_URL}`,
    '      icon: external',
    '      variant: minimal',
    '---',
    '',
    '## Two Interfaces, One Sovereign Engine',
    '',
    'SensAI combines two complementary interfaces built to explore the history of Ancient China\'s 7 Warring States:',
    '',
    '- **SensAI CLI**: The foundational roleplaying terminal featuring proactive RAG chronicle retrieval (*Shiji*, *Zhan Guo Ce*) and interactive turn-based tactical battle simulation (`/simulation [seed]`).',
    '- **SensAI Web Frontend**: A high-density modern cockpit built with React 19 and shadcn/ui, featuring token-by-token SSE streaming, dynamic interactive forms (`sensai-form`), Human-in-the-loop cryptographic action validation, and live token budget counters.',
  ].join('\n');

  fs.mkdirSync(path.join(contentDir, 'fr'), { recursive: true });
  fs.mkdirSync(path.join(contentDir, 'en'), { recursive: true });
  fs.writeFileSync(path.join(contentDir, 'fr', 'index.md'), frLanding);
  fs.writeFileSync(path.join(contentDir, 'en', 'index.md'), enLanding);

  let count = 0;
  for (const lang of ['fr', 'en']) {
    for (const page of PAGES) {
      const raw = readDoc(lang, page.src);
      if (!raw) {
        console.warn(`  [skip] ${lang}/${page.slug} (docs/${lang}/${page.src} absent)`);
        continue;
      }
      const targetFile = path.join(contentDir, lang, `${page.slug}.md`);
      fs.mkdirSync(path.dirname(targetFile), { recursive: true });
      const title = page.title[lang];
      const desc = page.description[lang];
      const fm = frontmatter(title, desc, `docs/${lang}/${page.src}`, page.order);
      fs.writeFileSync(targetFile, `${fm}${cleanMarkdown(raw).trim()}\n`);
      count++;
    }
  }

  console.log(`sync-docs: ${count} page(s) synchronisée(s) vers ${contentDir} (FR & EN)`);
}

sync();

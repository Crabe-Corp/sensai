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
    src: 'docs/README.md',
    title: 'Vue d\'ensemble & Vision',
    description: 'Introduction générale au projet SensAI, ses objectifs et ses composants.',
    order: 1,
  },
  {
    slug: 'architecture',
    src: 'docs/README.md',
    title: 'Architecture Globale',
    description: 'Architecture des systèmes SensAI, flux de données et composants.',
    order: 2,
  },
  {
    slug: 'interfaces/cli',
    src: 'docs/cli.md',
    title: 'Guide du CLI SensAI',
    description: 'Commandes, options, modes /encyclopedia et /simulation.',
    order: 1,
  },
  {
    slug: 'interfaces/frontend',
    src: 'docs/frontend.md',
    title: 'SensAI Web Frontend',
    description: 'Interface web React 19, Tailwind v4, shadcn/ui et design Dark Obsidian.',
    order: 2,
  },
  {
    slug: 'interfaces/frontend-architecture',
    src: 'docs/frontend-architecture.md',
    title: 'Architecture & Protocoles Frontend',
    description: 'Streaming NDJSON, formulaires ask_user_form, Human-in-the-loop et budget de tokens.',
    order: 3,
  },
  {
    slug: 'features/tools',
    src: 'docs/tools-guide.md',
    title: 'Système d\'Outils & MCP',
    description: 'Création d\'outils avec @tool, registre dynamique et serveurs MCP.',
    order: 1,
  },
  {
    slug: 'features/rag-and-cache',
    src: 'docs/rag-and-cache.md',
    title: 'RAG & Cache Sémantique',
    description: 'Vectorisation Qdrant des manuscrits historiques et cache sémantique à deux niveaux.',
    order: 2,
  },
  {
    slug: 'project/contributing',
    src: 'docs/contributing.md',
    title: 'Guide du Contributeur',
    description: 'Conventions de code, contributeurs, standards de test et cycle de vie des PRs.',
    order: 1,
  },
];

function read(rel) {
  const file = path.join(repoRoot, rel);
  if (!fs.existsSync(file)) return null;
  return fs.readFileSync(file, 'utf8');
}

function frontmatter(page) {
  const lines = ['---'];
  lines.push(`title: ${JSON.stringify(page.title)}`);
  if (page.description) lines.push(`description: ${JSON.stringify(page.description)}`);
  if (page.src) lines.push(`editUrl: ${JSON.stringify(`${REPO_URL}/edit/${REPO_BRANCH}/${page.src}`)}`);
  lines.push('sidebar:');
  lines.push(`  order: ${page.order}`);
  lines.push('---', '');
  return lines.join('\n');
}

function cleanMarkdown(content) {
  return content.replace(/^#\s+[^\n]+\n+/, '');
}

function sync() {
  fs.rmSync(contentDir, { recursive: true, force: true });
  fs.mkdirSync(contentDir, { recursive: true });

  const indexLanding = [
    '---',
    'title: SensAI',
    'description: Assistant IA modulaire & agentique inspiré des 7 Royaumes Combattants de la Chine antique.',
    'template: splash',
    'editUrl: false',
    'hero:',
    '  title: SensAI',
    '  tagline: Assistant IA modulaire, agentique et souverain. Explorez le lore historique des 7 Royaumes Combattants ou lancez des simulations de guerre tactiques.',
    '  image:',
    '    file: ../../assets/logo.svg',
    '  actions:',
    `    - text: Découvrir le projet`,
    `      link: ${BASE}/overview/`,
    '      icon: right-arrow',
    `    - text: Guide du CLI`,
    `      link: ${BASE}/interfaces/cli/`,
    '      icon: laptop',
    '      variant: secondary',
    `    - text: Interface Frontend`,
    `      link: ${BASE}/interfaces/frontend/`,
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

  fs.writeFileSync(path.join(contentDir, 'index.md'), indexLanding);

  let count = 0;
  for (const page of PAGES) {
    const raw = read(page.src);
    if (!raw) {
      console.warn(`  [skip] ${page.slug} (${page.src} absent)`);
      continue;
    }
    const targetFile = path.join(contentDir, `${page.slug}.md`);
    fs.mkdirSync(path.dirname(targetFile), { recursive: true });
    fs.writeFileSync(targetFile, `${frontmatter(page)}${cleanMarkdown(raw).trim()}\n`);
    count++;
  }
  console.log(`sync-docs: ${count} page(s) synchronisée(s) vers ${contentDir}`);
}

sync();

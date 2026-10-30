// Configuration partagée pour le site de documentation SensAI.
export const SITE = process.env.DOCS_SITE ?? 'https://lucaslhomme.github.io';
export const BASE = (process.env.DOCS_BASE ?? '/sensai').replace(/\/$/, '');
export const REPO_URL = 'https://github.com/Crabe-Corp/sensai';
export const REPO_BRANCH = process.env.DOCS_BRANCH ?? 'dev';

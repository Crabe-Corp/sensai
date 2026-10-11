import type { Conversation, Message } from '../types'
import { parseUserMessage } from './messageParser'

export type ExportFormat = 'md' | 'json' | 'txt'

function getExportFilename(conversation: Conversation | null, extension: ExportFormat): string {
  const baseTitle = (conversation?.title || 'conversation')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'conversation'

  const dateStr = new Date().toISOString().slice(0, 10)
  return `${baseTitle}-${dateStr}.${extension}`
}

export function formatConversationAsMarkdown(
  conversation: Conversation | null,
  messages: Message[]
): string {
  const title = conversation?.title || 'Discussion SensAI'
  const dateStr = conversation?.created_at
    ? new Date(conversation.created_at).toLocaleString('fr-FR')
    : new Date().toLocaleString('fr-FR')
  const model = conversation?.model_name || 'qwen3:0.6b'
  const mode = conversation?.mode === 'work' ? 'Collaboratif (Work)' : 'Solo'
  const totalTokens = conversation?.total_tokens || messages.reduce((acc, m) => acc + (m.total_tokens || 0), 0)

  let md = `# ${title}\n\n`
  md += `- **Date :** ${dateStr}\n`
  md += `- **Modèle :** ${model}\n`
  md += `- **Mode :** ${mode}\n`
  md += `- **Total Tokens :** ${totalTokens}\n`
  md += `- **Nombre de messages :** ${messages.length}\n\n`
  md += `---\n\n`

  for (const msg of messages) {
    const isUser = msg.role === 'user'
    const { cleanContent, attachments } = isUser
      ? parseUserMessage(msg.content, msg.attachments)
      : { cleanContent: msg.content, attachments: msg.attachments || [] }

    const sender = msg.sender_name || (isUser ? 'Vous' : 'SensAI')
    const roleLabel = isUser ? 'Utilisateur' : 'Assistant'
    const msgTime = msg.created_at ? new Date(msg.created_at).toLocaleTimeString('fr-FR') : ''

    const header = msgTime
      ? `### ${sender} [${roleLabel}] - ${msgTime}`
      : `### ${sender} [${roleLabel}]`

    md += `${header}\n\n`
    if (attachments.length > 0) {
      const attsStr = attachments.map((a) => `${a.name}${a.sizeStr ? ` (${a.sizeStr})` : ''}`).join(', ')
      md += `*Fichier(s) joint(s) : ${attsStr}*\n\n`
    }
    if (cleanContent) {
      md += `${cleanContent.trim()}\n\n`
    }

    if (msg.total_tokens > 0) {
      md += `*Tokens : ${msg.total_tokens} (Prompt: ${msg.prompt_tokens}, Réponse: ${msg.completion_tokens})*\n\n`
    }
    md += `---\n\n`
  }

  return md
}

export function formatConversationAsJson(
  conversation: Conversation | null,
  messages: Message[]
): string {
  const exportData = {
    id: conversation?.id || null,
    title: conversation?.title || 'Discussion SensAI',
    mode: conversation?.mode || 'solo',
    model_name: conversation?.model_name || 'qwen3:0.6b',
    tools_enabled: conversation?.tools_enabled || [],
    total_tokens: conversation?.total_tokens || messages.reduce((acc, m) => acc + (m.total_tokens || 0), 0),
    created_at: conversation?.created_at || null,
    exported_at: new Date().toISOString(),
    messages: messages.map((m) => {
      const isUser = m.role === 'user'
      const { cleanContent, attachments } = isUser
        ? parseUserMessage(m.content, m.attachments)
        : { cleanContent: m.content, attachments: m.attachments || [] }

      return {
        id: m.id,
        role: m.role,
        sender_name: m.sender_name || (isUser ? 'Vous' : 'SensAI'),
        content: cleanContent,
        attachments: attachments.length > 0 ? attachments : undefined,
        prompt_tokens: m.prompt_tokens,
        completion_tokens: m.completion_tokens,
        total_tokens: m.total_tokens,
        created_at: m.created_at || null,
      }
    }),
  }

  return JSON.stringify(exportData, null, 2)
}

export function formatConversationAsText(
  conversation: Conversation | null,
  messages: Message[]
): string {
  const title = conversation?.title || 'Discussion SensAI'
  const dateStr = conversation?.created_at
    ? new Date(conversation.created_at).toLocaleString('fr-FR')
    : new Date().toLocaleString('fr-FR')
  const model = conversation?.model_name || 'qwen3:0.6b'
  const mode = conversation?.mode === 'work' ? 'Collaboratif (Work)' : 'Solo'
  const totalTokens = conversation?.total_tokens || messages.reduce((acc, m) => acc + (m.total_tokens || 0), 0)

  const separator = '='.repeat(80)
  const line = '-'.repeat(80)

  let txt = `${separator}\n`
  txt += `SENSAI - EXPORT DE CONVERSATION\n`
  txt += `${separator}\n`
  txt += `Titre       : ${title}\n`
  txt += `Date        : ${dateStr}\n`
  txt += `Mode        : ${mode}\n`
  txt += `Modèle      : ${model}\n`
  txt += `Total Tokens: ${totalTokens}\n`
  txt += `Messages    : ${messages.length}\n`
  txt += `${separator}\n\n`

  for (const msg of messages) {
    const isUser = msg.role === 'user'
    const { cleanContent, attachments } = isUser
      ? parseUserMessage(msg.content, msg.attachments)
      : { cleanContent: msg.content, attachments: msg.attachments || [] }

    const sender = msg.sender_name || (isUser ? 'Vous' : 'SensAI')
    const roleLabel = isUser ? 'Utilisateur' : 'Assistant'
    const msgTime = msg.created_at ? ` [${new Date(msg.created_at).toLocaleTimeString('fr-FR')}]` : ''

    txt += `[${sender} - ${roleLabel}]${msgTime} :\n`
    if (attachments.length > 0) {
      const attsStr = attachments.map((a) => `${a.name}${a.sizeStr ? ` (${a.sizeStr})` : ''}`).join(', ')
      txt += `Fichier(s) joint(s) : ${attsStr}\n`
    }
    if (cleanContent) {
      txt += `${cleanContent.trim()}\n\n`
    } else {
      txt += '\n'
    }
    txt += `${line}\n\n`
  }

  return txt
}

export function exportConversation(
  conversation: Conversation | null,
  messages: Message[],
  format: ExportFormat
): void {
  let content = ''
  let mimeType = 'text/plain;charset=utf-8'

  switch (format) {
    case 'md':
      content = formatConversationAsMarkdown(conversation, messages)
      mimeType = 'text/markdown;charset=utf-8'
      break
    case 'json':
      content = formatConversationAsJson(conversation, messages)
      mimeType = 'application/json;charset=utf-8'
      break
    case 'txt':
      content = formatConversationAsText(conversation, messages)
      mimeType = 'text/plain;charset=utf-8'
      break
  }

  const filename = getExportFilename(conversation, format)
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}


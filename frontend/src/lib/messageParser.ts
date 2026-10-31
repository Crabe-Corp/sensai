import type { MessageAttachment, FormSpec, ConfirmationSpec } from '../types'

export interface ParsedAttachment {
  name: string
  size?: number
  sizeStr?: string
}

export interface ParsedUserMessage {
  cleanContent: string
  attachments: ParsedAttachment[]
}

const ATTACHMENT_PATTERN =
  /\[Fichier joint\s*:\s*([^\]\(\)]+?)(?:\s*\(([^)]+)\))?\](?:\s*--- Début du contenu de [^\n\r]+ ---\s*[\s\S]*?\s*--- Fin du contenu de [^\n\r]+ ---)?/g

export function parseUserMessage(
  content: string,
  existingAttachments?: MessageAttachment[]
): ParsedUserMessage {
  if (!content) {
    return {
      cleanContent: '',
      attachments: existingAttachments || [],
    }
  }

  const extractedAttachments: ParsedAttachment[] = []
  let match: RegExpExecArray | null
  const regex = new RegExp(ATTACHMENT_PATTERN)

  while ((match = regex.exec(content)) !== null) {
    const name = match[1].trim()
    const sizeStr = match[2]?.trim()
    extractedAttachments.push({
      name,
      sizeStr,
    })
  }

  if (extractedAttachments.length > 0) {
    let cleanContent = content.replace(ATTACHMENT_PATTERN, '').trim()
    if (cleanContent.startsWith('Fichier(s) joint(s) :')) {
      cleanContent = ''
    }
    return {
      cleanContent,
      attachments:
        existingAttachments && existingAttachments.length > 0
          ? existingAttachments
          : extractedAttachments,
    }
  }

  return {
    cleanContent: content,
    attachments: existingAttachments || [],
  }
}


// --- Formulaires posés par l'agent (outil ask_user_form) ---

const FORM_BLOCK_PATTERN = /```sensai-form\n([\s\S]*?)\n```/

export interface ParsedFormMessage {
  text: string
  form: FormSpec | null
}

export function parseFormMessage(content: string): ParsedFormMessage {
  const match = FORM_BLOCK_PATTERN.exec(content)
  if (!match) return { text: content, form: null }
  try {
    const form = JSON.parse(match[1]) as FormSpec
    if (!Array.isArray(form.questions) || form.questions.length === 0) {
      return { text: content, form: null }
    }
    return { text: content.replace(FORM_BLOCK_PATTERN, '').trim(), form }
  } catch {
    return { text: content, form: null }
  }
}

// Pendant le streaming : masque le bloc formulaire (complet ou en cours d'écriture)
export function stripFormBlock(content: string): { text: string; formPending: boolean } {
  const start = content.indexOf('```sensai-form')
  if (start === -1) return { text: content, formPending: false }
  return { text: content.slice(0, start).trim(), formPending: true }
}

export function formatFormAnswers(form: FormSpec, answers: Record<string, string | boolean>): string {
  const lines = form.questions
    .filter((q) => answers[q.id] !== undefined && answers[q.id] !== '')
    .map((q) => {
      const value = answers[q.id]
      return `- ${q.label} : ${typeof value === 'boolean' ? (value ? 'Oui' : 'Non') : value}`
    })
  return `Réponses au formulaire « ${form.title} » :\n${lines.join('\n')}`
}


// --- Confirmations d'actions sensibles (Human-in-the-Loop [A3]) ---

const CONFIRM_BLOCK_PATTERN = /```sensai-confirm\n([\s\S]*?)\n```/

export interface ParsedConfirmMessage {
  text: string
  confirmation: ConfirmationSpec | null
}

export function parseConfirmMessage(content: string): ParsedConfirmMessage {
  if (!content) return { text: '', confirmation: null }

  const match = CONFIRM_BLOCK_PATTERN.exec(content)
  if (match) {
    try {
      const data = JSON.parse(match[1])
      const summary = data.summary || data.title || data.message || "Confirmation requise pour une action destructive"
      const confirmation: ConfirmationSpec = {
        action_id: data.action_id || data.id,
        tool_name: data.tool_name || data.tool,
        summary,
        action_type: data.action_type,
        details: data.details,
      }
      return { text: content.replace(CONFIRM_BLOCK_PATTERN, '').trim(), confirmation }
    } catch {
      return { text: content, confirmation: null }
    }
  }

  return { text: content, confirmation: null }
}

export function stripConfirmBlock(content: string): { text: string; confirmPending: boolean } {
  const start = content.indexOf('```sensai-confirm')
  if (start === -1) return { text: content, confirmPending: false }
  return { text: content.slice(0, start).trim(), confirmPending: true }
}

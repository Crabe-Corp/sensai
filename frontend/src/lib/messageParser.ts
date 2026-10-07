import type { MessageAttachment } from '../types'

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


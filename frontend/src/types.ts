export interface User {
  id: number
  username: string
  created_at?: string
}

export interface ConversationMember {
  user_id: number
  username: string
  role: string
}

export interface Conversation {
  id: string
  title: string
  mode: 'solo' | 'work'
  model_name: string
  tools_enabled: string[]
  total_tokens: number
  message_count?: number
  is_owner?: boolean
  created_at?: string
  updated_at?: string
  members?: ConversationMember[]
}

export interface MessageAttachment {
  name: string
  size?: number
  sizeStr?: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  sender_name?: string
  content: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  created_at?: string
  attachments?: MessageAttachment[]
}

export interface AttachedFile {
  id: string
  file: File
  name: string
  size: number
  type: string
  content?: string
}

export interface ToolInfo {
  id: string
  name: string
  description: string
  parameters?: Record<string, any>
  icon: string
  category: string
}

export interface McpServer {
  id: string
  name: string
  description: string
  status: string
  endpoint: string
  tools_count: number
}


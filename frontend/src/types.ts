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
  parent_id?: string | null
  parent_title?: string | null
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
  interrupted?: boolean
  from_cache?: boolean
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
  visible?: boolean
}

export interface McpServer {
  id: string
  name: string
  description: string
  status: string
  endpoint: string
  tools_count: number
  tools?: string[]
}

export interface FormQuestion {
  id: string
  label: string
  type: 'text' | 'number' | 'boolean' | 'choice'
  required: boolean
  options?: string[]
}

export interface FormSpec {
  title: string
  questions: FormQuestion[]
}

export interface ConfirmationSpec {
  action_id?: string
  tool_name?: string
  summary: string
  action_type?: 'file_write' | 'db_update' | string
  details?: Record<string, any> | string
}

export interface Persona {
  id: string
  name: string
  description: string
  system_prompt: string
  prompt?: string
}

import type { Conversation, Message, ToolInfo, McpServer, User } from '../types'

const TOKEN_KEY = 'sensai_auth_token'

export const authStorage = {
  getToken: (): string | null => localStorage.getItem(TOKEN_KEY),
  setToken: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clearToken: () => localStorage.removeItem(TOKEN_KEY),
}

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = authStorage.getToken()
  const headers = new Headers(options.headers || {})
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(endpoint, {
    ...options,
    headers,
  })

  if (!response.ok) {
    let errorDetail = 'Une erreur est survenue'
    try {
      const errJson = await response.json()
      errorDetail = errJson.detail || errorDetail
    } catch {
      // ignore
    }
    throw new Error(errorDetail)
  }

  return response.json()
}

export const api = {
  // Auth
  async register(username: string, password: string):Promise<{ access_token: string; user: User }> {
    const res = await apiFetch<{ access_token: string; user: User }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    authStorage.setToken(res.access_token)
    return res
  },

  async login(username: string, password: string): Promise<{ access_token: string; user: User }> {
    const res = await apiFetch<{ access_token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    authStorage.setToken(res.access_token)
    return res
  },

  async getMe(): Promise<User> {
    return apiFetch<User>('/api/auth/me')
  },

  async updateSettings(data: { username?: string; new_password?: string; current_password: string }): Promise<{ success: boolean; user: User; access_token: string }> {
    const res = await apiFetch<{ success: boolean; user: User; access_token: string }>('/api/auth/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    })
    if (res.access_token) {
      authStorage.setToken(res.access_token)
    }
    return res
  },

  // Conversations
  async listConversations(): Promise<Conversation[]> {
    return apiFetch<Conversation[]>('/api/conversations')
  },

  async createConversation(data: { title?: string; mode?: 'solo' | 'work'; model_name?: string; tools_enabled?: string[] }): Promise<Conversation> {
    return apiFetch<Conversation>('/api/conversations', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  async getConversation(id: string): Promise<Conversation & { messages: Message[] }> {
    return apiFetch<Conversation & { messages: Message[] }>(`/api/conversations/${id}`)
  },

  async deleteConversation(id: string): Promise<{ success: boolean }> {
    return apiFetch<{ success: boolean }>(`/api/conversations/${id}`, {
      method: 'DELETE',
    })
  },

  async addMember(conversationId: string, username: string, role = 'editor'): Promise<{ success: boolean; message: string }> {
    return apiFetch<{ success: boolean; message: string }>(`/api/conversations/${conversationId}/members`, {
      method: 'POST',
      body: JSON.stringify({ username, role }),
    })
  },

  // Models & Tools
  async getModels(): Promise<{ models: string[]; default: string }> {
    return apiFetch<{ models: string[]; default: string }>('/api/models')
  },

  async getTools(): Promise<ToolInfo[]> {
    return apiFetch<ToolInfo[]>('/api/models/tools')
  },

  async getModelConfig(): Promise<{ model_name: string; temperature: number; active_tools: string[] }> {
    return apiFetch<{ model_name: string; temperature: number; active_tools: string[] }>('/api/models/config')
  },

  async saveModelConfig(config: { model_name: string; temperature?: number; active_tools?: string[] }): Promise<{ success: boolean }> {
    return apiFetch<{ success: boolean }>('/api/models/config', {
      method: 'POST',
      body: JSON.stringify(config),
    })
  },

  // MCP
  async getMcpServers(): Promise<{ servers: McpServer[]; total: number }> {
    return apiFetch<{ servers: McpServer[]; total: number }>('/api/mcp/servers')
  },

  async addMcpServer(data: { name: string; description?: string; endpoint: string }): Promise<{ success: boolean; server: McpServer }> {
    return apiFetch<{ success: boolean; server: McpServer }>('/api/mcp/servers', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  // Progressive streaming chat
  async streamChat(
    conversationId: string,
    params: { content: string; model?: string; tools_enabled?: string[] },
    onChunk: (chunk: string) => void,
    onDone: (data: { message_id: string; prompt_tokens: number; completion_tokens: number; total_tokens: number; conversation_total_tokens: number }) => void,
    onError: (err: Error) => void
  ) {
    const token = authStorage.getToken()
    try {
      const response = await fetch(`/api/conversations/${conversationId}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(params),
      })

      if (!response.ok) {
        throw new Error(`Erreur HTTP: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('Flux de réponse non lisible')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed) continue
          try {
            const parsed = JSON.parse(trimmed)
            if (parsed.type === 'chunk') {
              onChunk(parsed.content)
            } else if (parsed.type === 'done') {
              onDone(parsed)
            }
          } catch {
            // ignore non-json chunk
          }
        }
      }

      if (buffer.trim()) {
        try {
          const parsed = JSON.parse(buffer.trim())
          if (parsed.type === 'done') {
            onDone(parsed)
          }
        } catch {
          // ignore
        }
      }
    } catch (err: any) {
      onError(err instanceof Error ? err : new Error(String(err)))
    }
  },
}

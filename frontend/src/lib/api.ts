import type { Conversation, Message, ToolInfo, McpServer, User } from '../types'

const TOKEN_KEY = 'sensai_auth_token'

export const authStorage = {
  getToken: (): string | null => localStorage.getItem(TOKEN_KEY),
  setToken: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clearToken: () => localStorage.removeItem(TOKEN_KEY),
}

export const UNAUTHORIZED_EVENT = 'sensai:unauthorized'

// Token expiré/invalide : on le purge et on prévient l'application pour revenir à l'écran de connexion
function handleUnauthorized(endpoint: string) {
  if (endpoint.startsWith('/api/auth/login') || endpoint.startsWith('/api/auth/register')) return
  authStorage.clearToken()
  window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
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
    if (response.status === 401) handleUnauthorized(endpoint)
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

  async exportConversation(id: string, format: 'md' | 'json' | 'txt' = 'md'): Promise<Blob> {
    const token = authStorage.getToken()
    const headers = new Headers()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    const response = await fetch(`/api/conversations/${id}/export?format=${format}`, {
      headers,
    })
    if (!response.ok) {
      throw new Error("Erreur lors de l'export de la conversation")
    }
    return response.blob()
  },

  async uploadFile(conversationId: string, file: File): Promise<{ success: boolean; filename: string; size: number; content_type: string; is_text: boolean; preview?: string }> {
    const token = authStorage.getToken()
    const headers = new Headers()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(`/api/conversations/${conversationId}/upload`, {
      method: 'POST',
      headers,
      body: formData,
    })

    if (!response.ok) {
      let detail = 'Erreur lors du téléversement'
      try {
        const err = await response.json()
        detail = err.detail || detail
      } catch {
        // ignore
      }
      throw new Error(detail)
    }

    return response.json()
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

  async deleteMcpServer(serverId: string): Promise<{ success: boolean; message?: string }> {
    return apiFetch<{ success: boolean; message?: string }>(`/api/mcp/servers/${serverId}`, {
      method: 'DELETE',
    })
  },

  async branchConversation(
    conversationId: string,
    messageId: string,
    title?: string,
    content?: string
  ): Promise<Conversation & { messages: Message[] }> {
    return apiFetch<Conversation & { messages: Message[] }>(`/api/conversations/${conversationId}/branch`, {
      method: 'POST',
      body: JSON.stringify({ message_id: messageId, title, content }),
    })
  },

  async truncateConversation(
    conversationId: string,
    messageId: string,
    content?: string
  ): Promise<{ success: boolean; remaining_messages: number; total_tokens: number }> {
    return apiFetch<{ success: boolean; remaining_messages: number; total_tokens: number }>(`/api/conversations/${conversationId}/truncate`, {
      method: 'POST',
      body: JSON.stringify({ message_id: messageId, content }),
    })
  },

  // Progressive streaming chat
  async streamChat(
    conversationId: string,
    params: { content: string; model?: string; tools_enabled?: string[]; system_instruction?: string },
    onChunk: (chunk: string) => void,
    onDone: (data: { message_id: string; user_message_id?: string; prompt_tokens: number; completion_tokens: number; total_tokens: number; conversation_total_tokens: number }) => void,
    onError: (err: Error) => void,
    signal?: AbortSignal,
    onAbort?: (accumulatedText: string) => void,
    onStart?: (data: { user_message_id: string }) => void
  ) {
    const token = authStorage.getToken()
    let accumulatedText = ''
    try {
      const response = await fetch(`/api/conversations/${conversationId}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(params),
        signal,
      })

      if (!response.ok) {
        if (response.status === 401) {
          handleUnauthorized(`/api/conversations/${conversationId}/chat`)
          throw new Error('Session expirée, veuillez vous reconnecter')
        }
        throw new Error(`Erreur HTTP: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('Flux de réponse non lisible')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        if (signal?.aborted) {
          reader.cancel().catch(() => {})
          if (onAbort) onAbort(accumulatedText)
          return
        }

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
            if (parsed.type === 'start') {
              if (parsed.user_message_id && onStart) {
                onStart(parsed)
              }
            } else if (parsed.type === 'chunk') {
              accumulatedText += parsed.content
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
      if (signal?.aborted || err?.name === 'AbortError' || err?.message?.toLowerCase().includes('abort')) {
        if (onAbort) {
          onAbort(accumulatedText)
        }
        return
      }
      onError(err instanceof Error ? err : new Error(String(err)))
    }
  },
}

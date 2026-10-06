import { useState, useEffect, useRef } from 'react'
import { AuthPage } from './components/AuthPage'
import { Sidebar } from './components/Sidebar'
import { ChatView } from './components/ChatView'
import { RunSettingsPanel } from './components/RunSettingsPanel'
import { SettingsModal } from './components/SettingsModal'
import { ModelsModal } from './components/ModelsModal'
import { WorkInviteModal } from './components/WorkInviteModal'
import { api, authStorage } from './lib/api'
import type { Conversation, Message, User, AttachedFile } from './types'

export function App() {
  const [user, setUser] = useState<User | null>(null)
  const [loadingAuth, setLoadingAuth] = useState(true)

  // Navigation & Modales
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [modelsOpen, setModelsOpen] = useState(false)
  const [inviteModalOpen, setInviteModalOpen] = useState(false)
  const [runSettingsOpen, setRunSettingsOpen] = useState(false)

  // Données de discussion
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<Message[]>([])

  // Streaming, Modèles & Tools (Google AI Studio style)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [currentModel, setCurrentModel] = useState('qwen3:0.6b')
  const [modelsList, setModelsList] = useState<string[]>(['qwen3:0.6b'])
  const [activeTools, setActiveTools] = useState<string[]>(['structured_output'])
  const [systemInstruction, setSystemInstruction] = useState('')

  // WebSocket pour la collaboration temps réel (Mode Work)
  const wsRef = useRef<WebSocket | null>(null)

  // Initialisation de la session au chargement
  useEffect(() => {
    const initAuth = async () => {
      const token = authStorage.getToken()
      if (token) {
        try {
          const me = await api.getMe()
          setUser(me)
          await loadInitialData()
        } catch {
          authStorage.clearToken()
          setUser(null)
        }
      }
      setLoadingAuth(false)
    }
    initAuth()
  }, [])

  // Chargement des conversations et configuration initiale
  const loadInitialData = async () => {
    try {
      const [convs, cfg, modelsData] = await Promise.all([
        api.listConversations(),
        api.getModelConfig().catch(() => ({ model_name: 'qwen3:0.6b', temperature: 0.7, active_tools: ['structured_output'] })),
        api.getModels().catch(() => ({ models: ['qwen3:0.6b'], default: 'qwen3:0.6b' })),
      ])
      setConversations(convs)
      setModelsList(modelsData.models || ['qwen3:0.6b'])
      setCurrentModel(cfg.model_name || 'qwen3:0.6b')
      const cleanTools = (cfg.active_tools || []).filter(
        (t: string) => t === 'structured_output' || t === 'Structured Output' || t === 'mcp_runner'
      )
      setActiveTools(cleanTools.length > 0 ? cleanTools : ['structured_output'])

      // Vérifier si une URL spécifique contient un ID de conversation (?c=...)
      const urlParams = new URLSearchParams(window.location.search)
      const targetId = urlParams.get('c')
      if (targetId) {
        const found = convs.find((c) => c.id === targetId)
        if (found) {
          await selectConversation(targetId)
          return
        }
      }

      // Règle demandée : à chaque connexion, on ouvre une nouvelle conversation
      await handleNewConversation('solo', cfg.model_name, cfg.active_tools)
    } catch {
      // ignore
    }
  }

  // Connexion WebSocket pour le mode "Work" (collaboration temps réel)
  useEffect(() => {
    if (!activeConversation || activeConversation.mode !== 'work') {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/api/ws/conversations/${activeConversation.id}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'new_message' && data.message) {
          setMessages((prev) => {
            if (prev.some((m) => m.id === data.message.id)) {
              return prev
            }
            return [...prev, data.message]
          })

          if (data.message.conversation_total_tokens !== undefined) {
            setActiveConversation((prev) =>
              prev ? { ...prev, total_tokens: data.message.conversation_total_tokens } : null
            )
            setConversations((prev) =>
              prev.map((c) =>
                c.id === activeConversation.id
                  ? { ...c, total_tokens: data.message.conversation_total_tokens }
                  : c
              )
            )
          }
        }
      } catch {
        // ignore
      }
    }

    return () => {
      ws.close()
    }
  }, [activeConversation?.id, activeConversation?.mode])

  // Sélection d'une conversation
  const selectConversation = async (id: string) => {
    try {
      const fullConv = await api.getConversation(id)
      setActiveConversation(fullConv)
      setMessages(fullConv.messages || [])
      const cleanConvTools = (fullConv.tools_enabled || []).filter(
        (t: string) => t === 'structured_output' || t === 'Structured Output' || t === 'mcp_runner'
      )
      setActiveTools(cleanConvTools)
      setCurrentModel(fullConv.model_name || 'qwen3:0.6b')
      window.history.replaceState(null, '', `?c=${id}`)
    } catch {
      // ignore
    }
  }

  // Création d'une nouvelle conversation
  const handleNewConversation = async (
    mode: 'solo' | 'work' = 'solo',
    model = currentModel,
    tools = activeTools
  ) => {
    try {
      const newConv = await api.createConversation({
        title: mode === 'work' ? 'Session Collaborative' : 'Nouvelle conversation',
        mode,
        model_name: model,
        tools_enabled: tools,
      })
      setConversations((prev) => [newConv, ...prev])
      setActiveConversation(newConv)
      setMessages([])
      window.history.replaceState(null, '', `?c=${newConv.id}`)
    } catch {
      // ignore
    }
  }

  // Suppression d'une conversation
  const handleDeleteConversation = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Supprimer cette conversation ?')) return
    try {
      await api.deleteConversation(id)
      setConversations((prev) => prev.filter((c) => c.id !== id))
      if (activeConversation?.id === id) {
        handleNewConversation('solo')
      }
    } catch {
      // ignore
    }
  }

  // Toggle d'outil en temps réel
  const handleToggleTool = (toolId: string) => {
    const idToToggle = toolId === 'Structured Output' ? 'structured_output' : toolId
    setActiveTools((prev) => {
      const exists =
        prev.includes(idToToggle) ||
        (idToToggle === 'structured_output' && prev.includes('Structured Output'))
      const updated = exists
        ? prev.filter((t) => t !== idToToggle && t !== 'Structured Output')
        : [...prev, idToToggle]

      setActiveConversation((curr) => (curr ? { ...curr, tools_enabled: updated } : null))
      return updated
    })
  }

  // Envoi d'un message avec streaming progressif, instruction système et tokens
  const handleSendMessage = async (text: string, files: AttachedFile[] = []) => {
    if (!activeConversation) return

    setIsStreaming(true)
    setStreamingText('')

    // Téléverser les fichiers en tâche de fond sur le serveur
    for (const f of files) {
      api.uploadFile(activeConversation.id, f.file).catch(() => {})
    }

    // Préparer le contenu avec les fichiers joints pour l'IA
    let payloadContent = text
    if (files.length > 0) {
      const formatBytes = (bytes: number) => {
        if (bytes < 1024) return `${bytes} o`
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`
        return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`
      }

      const filesContext = files
        .map((f) => {
          if (f.content) {
            return `[Fichier joint : ${f.name} (${formatBytes(f.size)})]\n--- Début du contenu de ${f.name} ---\n${f.content}\n--- Fin du contenu de ${f.name} ---`
          } else {
            return `[Fichier joint : ${f.name} (${formatBytes(f.size)})]`
          }
        })
        .join('\n\n')

      payloadContent = text.trim()
        ? `${filesContext}\n\n${text}`
        : filesContext
    }

    // Ajout optimiste du message utilisateur
    const optimisticUserMsg: Message = {
      id: `temp-${Date.now()}`,
      role: 'user',
      sender_name: user?.username || 'Vous',
      content: text,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      created_at: new Date().toISOString(),
      attachments: files.map((f) => ({ name: f.name, size: f.size })),
    }
    setMessages((prev) => [...prev, optimisticUserMsg])

    let accumulatedChunks = ''

    await api.streamChat(
      activeConversation.id,
      {
        content: payloadContent,
        model: currentModel,
        tools_enabled: activeTools,
        system_instruction: systemInstruction,
      },
      (chunk) => {
        accumulatedChunks += chunk
        setStreamingText(accumulatedChunks)
      },
      (doneData) => {
        setIsStreaming(false)
        setStreamingText('')

        const finalAssistantMsg: Message = {
          id: doneData.message_id,
          role: 'assistant',
          sender_name: 'SensAI',
          content: accumulatedChunks,
          prompt_tokens: doneData.prompt_tokens,
          completion_tokens: doneData.completion_tokens,
          total_tokens: doneData.total_tokens,
          created_at: new Date().toISOString(),
        }

        setMessages((prev) => [...prev, finalAssistantMsg])

        setActiveConversation((prev) =>
          prev ? { ...prev, total_tokens: doneData.conversation_total_tokens } : null
        )

        setConversations((prev) =>
          prev.map((c) =>
            c.id === activeConversation.id
              ? {
                  ...c,
                  total_tokens: doneData.conversation_total_tokens,
                  title:
                    c.title === 'Nouvelle conversation'
                      ? (text.trim() || files[0]?.name || 'Discussion').slice(0, 35) +
                        ((text.trim() || files[0]?.name || '').length > 35 ? '...' : '')
                      : c.title,
                }
              : c
          )
        )
      },
      (err) => {
        setIsStreaming(false)
        setStreamingText('')
        const errorMsg: Message = {
          id: `err-${Date.now()}`,
          role: 'assistant',
          sender_name: 'SensAI',
          content: `Erreur lors de la réponse : ${err.message}`,
          prompt_tokens: 0,
          completion_tokens: 0,
          total_tokens: 0,
          created_at: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, errorMsg])
      }
    )
  }

  // Déconnexion
  const handleLogout = () => {
    authStorage.clearToken()
    setUser(null)
    setActiveConversation(null)
    setMessages([])
    setSidebarOpen(false)
    setRunSettingsOpen(false)
  }

  if (loadingAuth) {
    return (
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center text-neutral-400 text-sm">
        Chargement de SensAI...
      </div>
    )
  }

  if (!user) {
    return (
      <AuthPage
        onSuccess={(loggedUser) => {
          setUser(loggedUser)
          loadInitialData()
        }}
      />
    )
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-neutral-950 font-sans">
      {/* Menu Hamburger latéral / Tiroir */}
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        user={user}
        conversations={conversations}
        activeId={activeConversation?.id || null}
        activeConversation={activeConversation}
        messages={messages}
        onSelectConversation={selectConversation}
        onNewConversation={(mode) => handleNewConversation(mode)}
        onDeleteConversation={handleDeleteConversation}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenModels={() => setModelsOpen(true)}
        onOpenMcp={() => setSettingsOpen(true)}
        onLogout={handleLogout}
      />

      {/* Zone centrale de discussion + Panneau latéral Run settings (Google AI Studio style) */}
      <div className="flex-1 flex h-full overflow-hidden">
        <ChatView
          conversation={activeConversation}
          messages={messages}
          isStreaming={isStreaming}
          streamingText={streamingText}
          activeTools={activeTools}
          onToggleTool={handleToggleTool}
          onSendMessage={handleSendMessage}
          onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
          onOpenInviteModal={() => setInviteModalOpen(true)}
          onToggleRunSettings={() => setRunSettingsOpen((prev) => !prev)}
          isRunSettingsOpen={runSettingsOpen}
        />

        {/* Panneau latéral Run Settings façon Google AI Studio */}
        <RunSettingsPanel
          isOpen={runSettingsOpen}
          onClose={() => setRunSettingsOpen(false)}
          model={currentModel}
          modelsList={modelsList}
          onModelChange={(m) => setCurrentModel(m)}
          activeTools={activeTools}
          onToggleTool={handleToggleTool}
          systemInstruction={systemInstruction}
          onSystemInstructionChange={setSystemInstruction}
          totalTokens={activeConversation?.total_tokens || 0}
        />
      </div>

      {/* Modal Paramètres & MCP */}
      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        user={user}
        onUserUpdated={(updated) => setUser(updated)}
      />

      {/* Modal Modèles & Tools faits main */}
      <ModelsModal
        isOpen={modelsOpen}
        onClose={() => setModelsOpen(false)}
        currentModel={currentModel}
        activeTools={activeTools}
        onModelChanged={(model) => setCurrentModel(model)}
        onToolsChanged={(tools) => setActiveTools(tools)}
      />

      {/* Modal d'invitation pour le mode Work */}
      <WorkInviteModal
        isOpen={inviteModalOpen}
        onClose={() => setInviteModalOpen(false)}
        conversationId={activeConversation?.id || null}
        onMemberAdded={() => {
          if (activeConversation) selectConversation(activeConversation.id)
        }}
      />
    </div>
  )
}

export default App

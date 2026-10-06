import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Menu,
  Sparkles,
  Users,
  Coins,
  UserPlus,
  Loader2,
  Bot,
  User,
  SlidersHorizontal,
  CornerDownLeft,
  X,
  Wrench,
  PanelRightOpen,
  PanelRightClose,
  Paperclip,
  AlertCircle,
  Plug,
} from 'lucide-react'
import type { Conversation, Message, AttachedFile } from '../types'
import { parseUserMessage } from '../lib/messageParser'

interface ChatViewProps {
  conversation: Conversation | null
  messages: Message[]
  isStreaming: boolean
  streamingText: string
  activeTools: string[]
  onToggleTool: (toolId: string) => void
  onSendMessage: (text: string, files?: AttachedFile[]) => void
  onToggleSidebar: () => void
  onOpenInviteModal: () => void
  onToggleRunSettings: () => void
  isRunSettingsOpen: boolean
}

const TOOL_DEFINITIONS = [
  {
    id: 'structured_output',
    name: 'Structured Output',
    shortName: 'Structured Output',
    source: 'Format JSON',
    description: 'Permet de générer des réponses au format JSON structuré.',
    icon: <Sparkles className="w-3.5 h-3.5 text-indigo-400" />,
  },
  {
    id: 'mcp_runner',
    name: 'Intégrations MCP',
    shortName: 'MCP',
    source: 'shadcn / Composio',
    description: 'Connecteurs et outils externes Model Context Protocol.',
    icon: <Plug className="w-3.5 h-3.5 text-sky-400" />,
  },
]

const MAX_FILE_SIZE = 25 * 1024 * 1024 // 25 Mo
const MAX_FILES_COUNT = 5 // 5 fichiers max

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`
}

function isJsonString(str: string): boolean {
  if (!str) return false
  const t = str.trim()
  if (!((t.startsWith('{') && t.endsWith('}')) || (t.startsWith('[') && t.endsWith(']')))) {
    return false
  }
  try {
    JSON.parse(t)
    return true
  } catch {
    return false
  }
}

function formatJson(str: string): string {
  try {
    return JSON.stringify(JSON.parse(str.trim()), null, 2)
  } catch {
    return str
  }
}

export function ChatView({
  conversation,
  messages,
  isStreaming,
  streamingText,
  activeTools,
  onToggleTool,
  onSendMessage,
  onToggleSidebar,
  onOpenInviteModal,
  onToggleRunSettings,
  isRunSettingsOpen,
}: ChatViewProps) {
  const [inputText, setInputText] = useState('')
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([])
  const [fileError, setFileError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Scroll automatique fluide vers le bas lors de l'arrivée progressive des tokens
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText, isStreaming])

  const handleAddFiles = async (filesList: FileList | File[]) => {
    setFileError(null)

    const incoming = Array.from(filesList)
    if (incoming.length === 0) return

    if (attachedFiles.length >= MAX_FILES_COUNT) {
      setFileError(`Vous avez déjà atteint la limite maximale de ${MAX_FILES_COUNT} fichiers.`)
      return
    }

    const availableSlots = MAX_FILES_COUNT - attachedFiles.length
    if (incoming.length > availableSlots) {
      setFileError(
        `Limite de ${MAX_FILES_COUNT} fichiers dépassée. Seuls les ${availableSlots} premier(s) fichier(s) ont été ajoutés.`
      )
    }

    const filesToProcess = incoming.slice(0, availableSlots)
    const newFiles: AttachedFile[] = []

    for (const file of filesToProcess) {
      if (file.size > MAX_FILE_SIZE) {
        setFileError(
          `Le fichier « ${file.name} » (${formatFileSize(file.size)}) dépasse la taille maximale autorisée de 25 Mo.`
        )
        continue
      }

      let textContent: string | undefined = undefined
      const isText =
        file.type.startsWith('text/') ||
        file.type === 'application/json' ||
        /\.(md|txt|json|csv|py|js|ts|tsx|jsx|html|css|yaml|yml|sh|sql|log)$/i.test(file.name)

      if (isText) {
        try {
          textContent = await file.text()
        } catch {
          // ignore
        }
      }

      newFiles.push({
        id: `${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
        file,
        name: file.name,
        size: file.size,
        type: file.type || 'application/octet-stream',
        content: textContent,
      })
    }

    if (newFiles.length > 0) {
      setAttachedFiles((prev) => [...prev, ...newFiles])
    }
  }

  const handleSend = () => {
    if ((!inputText.trim() && attachedFiles.length === 0) || isStreaming) return
    onSendMessage(inputText, attachedFiles)
    setInputText('')
    setAttachedFiles([])
    setFileError(null)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const totalTokens = conversation?.total_tokens || 0

  return (
    <div className="flex-1 flex flex-col h-screen bg-neutral-950 text-neutral-100 overflow-hidden">
      {/* Barre supérieure / En-tête */}
      <header className="h-14 border-b border-neutral-800 bg-neutral-900/60 backdrop-blur-md px-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          {/* Bouton Hamburger pour ouvrir le menu */}
          <button
            onClick={onToggleSidebar}
            title="Menu des conversations"
            className="p-2 rounded-lg bg-neutral-800/80 hover:bg-neutral-800 text-neutral-300 hover:text-white cursor-pointer transition-colors"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold truncate text-white">
                {conversation?.title || 'Nouvelle discussion'}
              </h2>

              {conversation?.mode === 'work' ? (
                <Badge
                  variant="outline"
                  className="bg-amber-950/40 border-amber-800 text-amber-300 text-[10px] px-2 py-0 gap-1 flex items-center"
                >
                  <Users className="w-3 h-3 text-amber-400" />
                  <span>Work (Collab temps réel)</span>
                </Badge>
              ) : (
                <Badge
                  variant="outline"
                  className="bg-indigo-950/30 border-indigo-800 text-indigo-300 text-[10px] px-2 py-0"
                >
                  Solo
                </Badge>
              )}
            </div>
            <div className="text-[10px] text-neutral-400 flex items-center gap-2">
              <span>Modèle : {conversation?.model_name || 'qwen3:0.6b'}</span>
              {conversation?.mode === 'work' && conversation.members && (
                <span>• {conversation.members.length} participant(s)</span>
              )}
            </div>
          </div>
        </div>

        {/* Boutons d'actions à droite : Inviter, Tokens et bouton Run settings */}
        <div className="flex items-center gap-2">
          {conversation?.mode === 'work' && (
            <Button
              size="sm"
              variant="outline"
              onClick={onOpenInviteModal}
              className="h-8 text-xs border-neutral-700 bg-neutral-800/80 hover:bg-neutral-800 text-neutral-200 gap-1.5 cursor-pointer"
            >
              <UserPlus className="w-3.5 h-3.5 text-amber-400" />
              <span className="hidden sm:inline">Inviter</span>
            </Button>
          )}

          {/* Badge global des tokens de la conversation */}
          <div
            title="Nombre total de tokens consommés dans cette conversation"
            className="hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full border border-neutral-800 bg-neutral-900 text-xs font-medium text-neutral-300"
          >
            <Coins className="w-3.5 h-3.5 text-amber-400" />
            <span>Tokens conv :</span>
            <span className="text-amber-300 font-bold font-mono">{totalTokens}</span>
          </div>

          {/* Bouton pour ouvrir / fermer le panneau latéral "Run settings" (Google AI Studio) */}
          <Button
            size="sm"
            variant="outline"
            onClick={onToggleRunSettings}
            title="Ouvrir les paramètres d'exécution et outils"
            className={`h-8 text-xs gap-1.5 border-neutral-700 cursor-pointer transition-colors ${
              isRunSettingsOpen
                ? 'bg-neutral-800 text-white border-neutral-600'
                : 'bg-neutral-900 text-neutral-300 hover:text-white hover:bg-neutral-800'
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5 text-indigo-400" />
            <span className="hidden md:inline">Run settings</span>
            {isRunSettingsOpen ? (
              <PanelRightClose className="w-3.5 h-3.5 text-neutral-400" />
            ) : (
              <PanelRightOpen className="w-3.5 h-3.5 text-neutral-400" />
            )}
          </Button>
        </div>
      </header>

      {/* Zone centrale : Liste des messages (centrée max-w-4xl) */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5">
        <div className="max-w-4xl w-full mx-auto space-y-5">
          {messages.length === 0 && !isStreaming ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto space-y-4 py-16">
              <div className="w-12 h-12 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shadow-lg">
                <Sparkles className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <h3 className="text-lg font-bold text-white">Prêt à commencer la conversation</h3>
                <p className="text-xs text-neutral-400">
                  Posez une question !
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full pt-2">
                <button
                  onClick={() => onSendMessage('Donne-moi 3 idées de projets avec leur nom et difficulté au format structuré.')}
                  className="p-3 text-left rounded-xl border border-neutral-800 bg-neutral-900/60 hover:bg-neutral-900 hover:border-neutral-700 text-xs text-neutral-300 transition-colors cursor-pointer"
                >
                  <div className="font-semibold text-white mb-0.5 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                    Sortie Structurée
                  </div>
                  Générer des données au format JSON
                </button>

                <button
                  onClick={() => onSendMessage("Explique comment fonctionne le mode Structured Output.")}
                  className="p-3 text-left rounded-xl border border-neutral-800 bg-neutral-900/60 hover:bg-neutral-900 hover:border-neutral-700 text-xs text-neutral-300 transition-colors cursor-pointer"
                >
                  <div className="font-semibold text-white mb-0.5 flex items-center gap-1.5">
                    <Wrench className="w-3.5 h-3.5 text-amber-400" />
                    Assistance SensAI
                  </div>
                  Poser une question technique
                </button>
              </div>
            </div>
          ) : (
            messages.map((msg) => {
              const isUser = msg.role === 'user'
              const { cleanContent: displayContent, attachments: displayAttachments } = isUser
                ? parseUserMessage(msg.content, msg.attachments)
                : { cleanContent: msg.content, attachments: msg.attachments || [] }

              return (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${isUser ? 'ml-auto justify-end' : 'mr-auto justify-start'}`}
                >
                  {!isUser && (
                    <div className="w-8 h-8 rounded-lg bg-indigo-950 border border-indigo-800/80 flex items-center justify-center text-indigo-300 shrink-0">
                      <Bot className="w-4 h-4" />
                    </div>
                  )}

                  <div className={`space-y-1.5 max-w-2xl ${isUser ? 'items-end' : 'items-start'}`}>
                    {/* Nom d'expéditeur */}
                    <div className={`text-[11px] text-neutral-400 ${isUser ? 'text-right' : 'text-left'}`}>
                      {msg.sender_name || (isUser ? 'Vous' : 'SensAI')}
                    </div>

                    {/* Bulle de texte */}
                    <div
                      className={`p-3.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap break-words ${
                        isUser
                          ? 'bg-indigo-600 text-white rounded-br-xs'
                          : 'bg-neutral-900 border border-neutral-800 text-neutral-100 rounded-bl-xs'
                      }`}
                    >
                      {/* Badges des fichiers joints */}
                      {displayAttachments && displayAttachments.length > 0 && (
                        <div className={`flex flex-wrap gap-1.5 ${displayContent ? 'mb-2.5' : ''}`}>
                          {displayAttachments.map((att, idx) => (
                            <div
                              key={idx}
                              className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border ${
                                isUser
                                  ? 'bg-indigo-700/80 border-indigo-500/60 text-white'
                                  : 'bg-neutral-800 border-neutral-700 text-neutral-200'
                              }`}
                            >
                              <Paperclip className="w-3 h-3 text-indigo-300 shrink-0" />
                              <span className="truncate max-w-44 font-mono">{att.name}</span>
                              {(att.sizeStr || (att.size !== undefined && att.size > 0)) && (
                                <span className="text-[10px] opacity-75 font-mono">
                                  ({att.sizeStr || (att.size ? formatFileSize(att.size) : '')})
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {displayContent ? (
                        !isUser && isJsonString(displayContent) ? (
                          <pre className="font-mono text-xs overflow-x-auto text-indigo-300 p-1">
                            {formatJson(displayContent)}
                          </pre>
                        ) : (
                          displayContent
                        )
                      ) : null}
                    </div>

                    {/* Badge de coût en tokens pour chaque réponse de l'IA */}
                    {!isUser && msg.total_tokens > 0 && (
                      <div className="flex items-center gap-1.5 text-[10px] text-neutral-400 bg-neutral-900/80 border border-neutral-800/80 px-2 py-0.5 rounded-md w-fit">
                        <Coins className="w-3 h-3 text-amber-400" />
                        <span>Coût : </span>
                        <span className="text-neutral-300 font-medium">Prompt : {msg.prompt_tokens}</span>
                        <span>•</span>
                        <span className="text-neutral-300 font-medium">Réponse : {msg.completion_tokens}</span>
                        <span>•</span>
                        <span className="text-amber-300 font-bold">Total : {msg.total_tokens} tokens</span>
                      </div>
                    )}
                  </div>

                  {isUser && (
                    <div className="w-8 h-8 rounded-lg bg-neutral-800 border border-neutral-700 flex items-center justify-center text-neutral-300 shrink-0">
                      <User className="w-4 h-4" />
                    </div>
                  )}
                </div>
              )
            })
          )}

          {/* Message en cours de streaming (apparition progressive en direct) */}
          {isStreaming && (
            <div className="flex gap-3 max-w-2xl mr-auto justify-start animate-fade-in">
              <div className="w-8 h-8 rounded-lg bg-indigo-950 border border-indigo-800/80 flex items-center justify-center text-indigo-300 shrink-0">
                <Bot className="w-4 h-4" />
              </div>

              <div className="space-y-1.5 max-w-xl">
                <div className="text-[11px] text-neutral-400 flex items-center gap-1.5">
                  <span>SensAI</span>
                  <span className="text-indigo-400 text-[10px] flex items-center gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Génération en cours...
                  </span>
                </div>

                <div className="p-3.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap break-words bg-neutral-900 border border-indigo-900/40 text-neutral-100 rounded-bl-xs shadow-md">
                  {streamingText || '...'}
                  <span className="inline-block w-1.5 h-4 ml-0.5 bg-indigo-400 animate-pulse align-middle"></span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Zone inférieure : Prompt Box Inspirée de Google AI Studio */}
      <footer className="p-4 sm:p-6 pt-0 bg-transparent shrink-0">
        <div className="max-w-4xl w-full mx-auto">
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setIsDragging(true)
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setIsDragging(false)
              if (e.dataTransfer.files) handleAddFiles(e.dataTransfer.files)
            }}
            className={`relative rounded-2xl border bg-neutral-900/90 shadow-2xl backdrop-blur-md transition-all focus-within:border-neutral-700 focus-within:ring-1 focus-within:ring-indigo-500/20 ${
              isDragging ? 'border-indigo-500 ring-2 ring-indigo-500/40 bg-indigo-950/20' : 'border-neutral-800'
            }`}
          >
            {/* Overlay visuel lors du glisser-déposer */}
            {isDragging && (
              <div className="absolute inset-0 z-30 bg-neutral-900/95 backdrop-blur-xs rounded-2xl border-2 border-dashed border-indigo-500 flex flex-col items-center justify-center pointer-events-none text-indigo-300 text-xs gap-1.5">
                <Paperclip className="w-6 h-6 animate-bounce text-indigo-400" />
                <span className="font-semibold text-white">Déposez vos fichiers ici</span>
                <span className="text-[11px] text-neutral-400">Taille maximale : 25 Mo par fichier (5 fichiers max)</span>
              </div>
            )}

            {/* Bannière d'erreur si un fichier dépasse 25 Mo */}
            {fileError && (
              <div className="mx-3.5 mt-3 p-2.5 rounded-lg bg-red-950/80 border border-red-800 text-red-200 text-xs flex items-center justify-between gap-2 animate-fade-in">
                <div className="flex items-center gap-2 min-w-0">
                  <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                  <span className="truncate">{fileError}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setFileError(null)}
                  className="p-1 hover:text-white cursor-pointer rounded-xs"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Chips des fichiers joints en attente d'envoi */}
            {attachedFiles.length > 0 && (
              <div className="flex flex-wrap gap-2 px-3.5 pt-3 pb-1">
                {attachedFiles.map((af) => (
                  <div
                    key={af.id}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-neutral-800/90 border border-neutral-700/80 text-xs text-neutral-200 shadow-xs animate-fade-in"
                  >
                    <Paperclip className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                    <span className="font-medium truncate max-w-44" title={af.name}>
                      {af.name}
                    </span>
                    <span className="text-[10px] text-neutral-400 font-mono">
                      ({formatFileSize(af.size)})
                    </span>
                    <button
                      type="button"
                      onClick={() => setAttachedFiles((prev) => prev.filter((f) => f.id !== af.id))}
                      className="p-0.5 rounded-sm hover:bg-neutral-700 text-neutral-400 hover:text-white transition-colors cursor-pointer ml-1"
                      title="Retirer ce fichier"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Zone de texte du prompt */}
            <div className="p-3.5 pb-2">
              <Textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  attachedFiles.length > 0
                    ? "Posez une question sur le(s) fichier(s) joint(s) ou ajoutez vos instructions..."
                    : "Tapez un prompt pour discuter avec SensAI ou invoquer un outil..."
                }
                rows={1}
                disabled={isStreaming}
                className="border-0 focus-visible:ring-0 resize-none min-h-[50px] max-h-36 bg-transparent text-sm text-neutral-100 placeholder:text-neutral-500 p-0 focus:outline-none"
              />
            </div>

            {/* Barre d'outils interne façon Google AI Studio */}
            <div className="flex items-center justify-between px-3 py-2 border-t border-neutral-800/70 bg-neutral-950/40 rounded-b-2xl gap-2">
              {/* À gauche : Bouton "Tools" + Bouton "Joindre" + Pills d'outils actifs */}
              <div className="flex items-center gap-2 overflow-x-auto min-w-0 pr-2">
                {/* Input fichier caché (max 25 Mo) */}
                <input
                  type="file"
                  multiple
                  ref={fileInputRef}
                  onChange={(e) => {
                    if (e.target.files) handleAddFiles(e.target.files)
                    e.target.value = ''
                  }}
                  className="hidden"
                />

                {/* Bouton Joindre un fichier */}
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={attachedFiles.length >= MAX_FILES_COUNT}
                  title={
                    attachedFiles.length >= MAX_FILES_COUNT
                      ? `Limite de ${MAX_FILES_COUNT} fichiers atteinte`
                      : `Ajouter des fichiers (max 25 Mo par fichier, ${MAX_FILES_COUNT} max)`
                  }
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-neutral-300 hover:text-white bg-neutral-800/90 hover:bg-neutral-800 border border-neutral-700/70 transition-colors cursor-pointer shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Paperclip className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Joindre</span>
                  {attachedFiles.length > 0 && (
                    <span className="w-auto px-1.5 h-4 rounded-full bg-indigo-600 text-[10px] font-bold text-white flex items-center justify-center font-mono">
                      {attachedFiles.length}/{MAX_FILES_COUNT}
                    </span>
                  )}
                </button>

                {/* Popover Bouton Tools (style Google AI Studio) */}
                <Popover>
                  <PopoverTrigger
                    type="button"
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-neutral-300 hover:text-white bg-neutral-800/90 hover:bg-neutral-800 border border-neutral-700/70 transition-colors cursor-pointer shrink-0"
                  >
                    <SlidersHorizontal className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Tools</span>
                    {activeTools.length > 0 && (
                      <span className="w-4 h-4 rounded-full bg-indigo-600 text-[10px] font-bold text-white flex items-center justify-center">
                        {activeTools.length}
                      </span>
                    )}
                  </PopoverTrigger>
                  <PopoverContent className="w-80 p-3 bg-neutral-900 border-neutral-800 text-neutral-100 shadow-2xl rounded-xl space-y-3 z-50">
                    <div className="flex items-center justify-between pb-2 border-b border-neutral-800">
                      <div className="text-xs font-semibold flex items-center gap-1.5">
                        <Wrench className="w-3.5 h-3.5 text-indigo-400" />
                        <span>Outils SensAI intégrés</span>
                      </div>
                      <span className="text-[10px] text-neutral-400">
                        {activeTools.length} actif{activeTools.length > 1 ? 's' : ''}
                      </span>
                    </div>

                    <div className="space-y-2">
                      {TOOL_DEFINITIONS.map((tool) => {
                        const isActive =
                          activeTools.includes(tool.id) ||
                          (tool.id === 'structured_output' && activeTools.includes('Structured Output'))
                        return (
                          <button
                            type="button"
                            key={tool.id}
                            onClick={() => onToggleTool(tool.id)}
                            className={`w-full p-2.5 rounded-lg border text-xs flex items-center justify-between gap-2.5 cursor-pointer transition-colors text-left ${
                              isActive
                                ? 'bg-neutral-800/90 border-indigo-500/50 text-white'
                                : 'bg-neutral-950/60 border-neutral-800 text-neutral-400 hover:text-neutral-200 hover:border-neutral-700'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <div className="p-1.5 rounded-md bg-neutral-900 border border-neutral-800 shrink-0">
                                {tool.icon}
                              </div>
                              <div className="min-w-0">
                                <div className="font-medium text-xs truncate text-neutral-200">
                                  {tool.name}
                                </div>
                                <div className="text-[10px] text-neutral-400 truncate">
                                  {tool.description}
                                </div>
                              </div>
                            </div>
                            <Switch
                              checked={isActive}
                              tabIndex={-1}
                              className="shrink-0 pointer-events-none"
                            />
                          </button>
                        )
                      })}
                    </div>
                  </PopoverContent>
                </Popover>

                {/* Badges d'outils actifs affichés directement à côté (Google AI Studio style!) */}
                {activeTools.map((toolId) => {
                  const tool = TOOL_DEFINITIONS.find(
                    (t) => t.id === toolId || (t.id === 'structured_output' && toolId === 'Structured Output')
                  )
                  if (!tool) return null
                  return (
                    <div
                      key={toolId}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-neutral-800 border border-neutral-700/80 text-xs font-medium text-neutral-200 shadow-xs shrink-0 animate-fade-in"
                    >
                      <span className="w-3.5 h-3.5 flex items-center justify-center">
                        {tool.icon}
                      </span>
                      <span className="text-xs">{tool.name}</span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          onToggleTool(toolId)
                        }}
                        className="p-0.5 rounded-sm hover:bg-neutral-700 text-neutral-400 hover:text-white transition-colors cursor-pointer ml-0.5"
                        title={`Désactiver ${tool.name}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  )
                })}
              </div>

              {/* À droite : Bouton Run / Envoyer (comme dans Google AI Studio) */}
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  onClick={handleSend}
                  disabled={(!inputText.trim() && attachedFiles.length === 0) || isStreaming}
                  size="sm"
                  className="h-8 px-3.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg gap-1.5 font-medium text-xs cursor-pointer disabled:opacity-50 transition-all shadow-md"
                >
                  {isStreaming ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Génération...</span>
                    </>
                  ) : (
                    <>
                      <span>Run</span>
                      <CornerDownLeft className="w-3.5 h-3.5 opacity-70" />
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

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
  Crown,
  Dice5,
  Calculator,
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
} from 'lucide-react'
import type { Conversation, Message } from '../types'

interface ChatViewProps {
  conversation: Conversation | null
  messages: Message[]
  isStreaming: boolean
  streamingText: string
  activeTools: string[]
  onToggleTool: (toolId: string) => void
  onSendMessage: (text: string) => void
  onToggleSidebar: () => void
  onOpenInviteModal: () => void
  onToggleRunSettings: () => void
  isRunSettingsOpen: boolean
}

const TOOL_DEFINITIONS = [
  {
    id: 'kingdom_stats',
    name: 'Statistiques Royaumes',
    shortName: 'Royaumes',
    source: 'SensAI Lore DB',
    description: 'Consulte l’or, l’armée et la diplomatie des factions.',
    icon: <Crown className="w-3.5 h-3.5 text-amber-400" />,
  },
  {
    id: 'dice_roller',
    name: 'Lancer de dés JDR',
    shortName: 'Dés JDR',
    source: 'Module Aléatoire 1d20/2d6',
    description: 'Tire des dés aléatoires pour tester des actions.',
    icon: <Dice5 className="w-3.5 h-3.5 text-indigo-400" />,
  },
  {
    id: 'calculator',
    name: 'Calculateur d’armées',
    shortName: 'Calculateur',
    source: 'Moteur Arithmétique',
    description: 'Calcule taxes, pertes de guerre et tributs.',
    icon: <Calculator className="w-3.5 h-3.5 text-emerald-400" />,
  },
]

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
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Scroll automatique fluide vers le bas lors de l'arrivée progressive des tokens
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText, isStreaming])

  const handleSend = () => {
    if (!inputText.trim() || isStreaming) return
    onSendMessage(inputText)
    setInputText('')
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
                  Posez une question, demandez des statistiques sur un royaume ou simulez un lancer de dés.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full pt-2">
                <button
                  onClick={() => onSendMessage('Quelles sont les statistiques du royaume de Valoria ?')}
                  className="p-3 text-left rounded-xl border border-neutral-800 bg-neutral-900/60 hover:bg-neutral-900 hover:border-neutral-700 text-xs text-neutral-300 transition-colors cursor-pointer"
                >
                  <div className="font-semibold text-white mb-0.5 flex items-center gap-1.5">
                    <Crown className="w-3.5 h-3.5 text-amber-400" />
                    Royaume de Valoria
                  </div>
                  Consulter trésorerie et armée
                </button>

                <button
                  onClick={() => onSendMessage("Lance un dé 1d20 pour tester mon initiative d'attaque.")}
                  className="p-3 text-left rounded-xl border border-neutral-800 bg-neutral-900/60 hover:bg-neutral-900 hover:border-neutral-700 text-xs text-neutral-300 transition-colors cursor-pointer"
                >
                  <div className="font-semibold text-white mb-0.5 flex items-center gap-1.5">
                    <Dice5 className="w-3.5 h-3.5 text-indigo-400" />
                    Lancer de dés
                  </div>
                  Simuler un jet 1d20 JDR
                </button>
              </div>
            </div>
          ) : (
            messages.map((msg) => {
              const isUser = msg.role === 'user'
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
                      {msg.content}
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
          <div className="relative rounded-2xl border border-neutral-800 bg-neutral-900/90 shadow-2xl backdrop-blur-md transition-all focus-within:border-neutral-700 focus-within:ring-1 focus-within:ring-indigo-500/20">
            {/* Zone de texte du prompt */}
            <div className="p-3.5 pb-2">
              <Textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Tapez un prompt pour discuter avec SensAI ou invoquer un outil..."
                rows={1}
                disabled={isStreaming}
                className="border-0 focus-visible:ring-0 resize-none min-h-[50px] max-h-36 bg-transparent text-sm text-neutral-100 placeholder:text-neutral-500 p-0 focus:outline-none"
              />
            </div>

            {/* Barre d'outils interne façon Google AI Studio */}
            <div className="flex items-center justify-between px-3 py-2 border-t border-neutral-800/70 bg-neutral-950/40 rounded-b-2xl gap-2">
              {/* À gauche : Bouton "Tools" avec Popover + Pills d'outils actifs */}
              <div className="flex items-center gap-2 overflow-x-auto min-w-0 pr-2">
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
                        const isActive = activeTools.includes(tool.id)
                        return (
                          <div
                            key={tool.id}
                            onClick={() => onToggleTool(tool.id)}
                            className={`p-2.5 rounded-lg border text-xs flex items-center justify-between gap-2.5 cursor-pointer transition-colors ${
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
                              onCheckedChange={() => onToggleTool(tool.id)}
                              className="shrink-0 cursor-pointer"
                            />
                          </div>
                        )
                      })}
                    </div>
                  </PopoverContent>
                </Popover>

                {/* Badges d'outils actifs affichés directement à côté (Google AI Studio style!) */}
                {activeTools.map((toolId) => {
                  const tool = TOOL_DEFINITIONS.find((t) => t.id === toolId)
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
                  disabled={!inputText.trim() || isStreaming}
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

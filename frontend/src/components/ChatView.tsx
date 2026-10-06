import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import {
  Menu,
  Send,
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
  Zap,
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

        {/* Compteur global de tokens de la conversation & bouton inviter */}
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
            className="flex items-center gap-1.5 px-3 py-1 rounded-full border border-neutral-800 bg-neutral-900 text-xs font-medium text-neutral-300"
          >
            <Coins className="w-3.5 h-3.5 text-amber-400" />
            <span>Tokens conv :</span>
            <span className="text-amber-300 font-bold">{totalTokens}</span>
          </div>
        </div>
      </header>

      {/* Zone centrale : Liste des messages de la discussion */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5">
        {messages.length === 0 && !isStreaming ? (
          <div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto space-y-4 py-12">
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
                onClick={() => onSendMessage("Quelles sont les statistiques du royaume de Valoria ?")}
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
                className={`flex gap-3 max-w-3xl ${isUser ? 'ml-auto justify-end' : 'mr-auto justify-start'}`}
              >
                {!isUser && (
                  <div className="w-8 h-8 rounded-lg bg-indigo-950 border border-indigo-800/80 flex items-center justify-center text-indigo-300 shrink-0">
                    <Bot className="w-4 h-4" />
                  </div>
                )}

                <div className={`space-y-1.5 max-w-xl ${isUser ? 'items-end' : 'items-start'}`}>
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
          <div className="flex gap-3 max-w-3xl mr-auto justify-start animate-fade-in">
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
                {/* Curseur clignotant simulant la frappe progressive */}
                <span className="inline-block w-1.5 h-4 ml-0.5 bg-indigo-400 animate-pulse align-middle"></span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Zone inférieure : Sélecteur de tools & Champ de saisie */}
      <footer className="p-4 border-t border-neutral-800 bg-neutral-900/80 backdrop-blur-md space-y-3 shrink-0">
        {/* Chips d'outils disponibles créés main dans le repo */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
          <span className="text-[11px] text-neutral-400 flex items-center gap-1 shrink-0 font-medium">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            Tools repo :
          </span>

          <button
            onClick={() => onToggleTool('kingdom_stats')}
            className={`px-2.5 py-1 rounded-full border text-[11px] flex items-center gap-1.5 cursor-pointer transition-colors ${
              activeTools.includes('kingdom_stats')
                ? 'bg-amber-950/60 border-amber-700 text-amber-300'
                : 'bg-neutral-950 border-neutral-800 text-neutral-400 hover:text-white'
            }`}
          >
            <Crown className="w-3 h-3" />
            <span>Statistiques Royaumes</span>
          </button>

          <button
            onClick={() => onToggleTool('dice_roller')}
            className={`px-2.5 py-1 rounded-full border text-[11px] flex items-center gap-1.5 cursor-pointer transition-colors ${
              activeTools.includes('dice_roller')
                ? 'bg-indigo-950/60 border-indigo-700 text-indigo-300'
                : 'bg-neutral-950 border-neutral-800 text-neutral-400 hover:text-white'
            }`}
          >
            <Dice5 className="w-3 h-3" />
            <span>Lancer de dés</span>
          </button>

          <button
            onClick={() => onToggleTool('calculator')}
            className={`px-2.5 py-1 rounded-full border text-[11px] flex items-center gap-1.5 cursor-pointer transition-colors ${
              activeTools.includes('calculator')
                ? 'bg-emerald-950/60 border-emerald-700 text-emerald-300'
                : 'bg-neutral-950 border-neutral-800 text-neutral-400 hover:text-white'
            }`}
          >
            <Calculator className="w-3 h-3" />
            <span>Calculateur</span>
          </button>
        </div>

        {/* Champ de saisie prompt avec textarea auto-expansible */}
        <div className="relative flex items-end gap-2 bg-neutral-950 border border-neutral-800 rounded-xl p-2 focus-within:border-indigo-500 transition-colors">
          <Textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Posez votre question ou invoquez un outil (Entrée pour envoyer, Maj+Entrée pour saut de ligne)..."
            rows={1}
            disabled={isStreaming}
            className="border-0 focus-visible:ring-0 resize-none min-h-[44px] max-h-32 bg-transparent text-sm text-neutral-100 placeholder:text-neutral-500 py-2.5"
          />

          <Button
            onClick={handleSend}
            disabled={!inputText.trim() || isStreaming}
            className="h-10 w-10 p-0 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shrink-0 cursor-pointer disabled:opacity-50"
          >
            {isStreaming ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
      </footer>
    </div>
  )
}

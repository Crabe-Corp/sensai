import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Plus,
  MessageSquare,
  Users,
  Settings,
  Cpu,
  Plug,
  Trash2,
  LogOut,
  Search,
  Coins,
  X
} from 'lucide-react'
import type { Conversation, User as UserType } from '../types'

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
  user: UserType
  conversations: Conversation[]
  activeId: string | null
  onSelectConversation: (id: string) => void
  onNewConversation: (mode?: 'solo' | 'work') => void
  onDeleteConversation: (id: string, e: React.MouseEvent) => void
  onOpenSettings: () => void
  onOpenModels: () => void
  onOpenMcp: () => void
  onLogout: () => void
}

export function Sidebar({
  isOpen,
  onClose,
  user,
  conversations,
  activeId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  onOpenSettings,
  onOpenModels,
  onOpenMcp,
  onLogout,
}: SidebarProps) {
  const [filterMode, setFilterMode] = useState<'all' | 'solo' | 'work'>('all')
  const [search, setSearch] = useState('')

  const filteredConversations = conversations.filter((c) => {
    if (filterMode !== 'all' && c.mode !== filterMode) return false
    if (search && !c.title.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  return (
    <>
      {/* Backdrop sombre sur mobile / tablettes */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 bg-black/60 backdrop-blur-xs z-40 transition-opacity"
        />
      )}

      {/* Drawer menu latéral */}
      <aside
        className={`fixed top-0 left-0 h-full w-80 bg-neutral-900 border-r border-neutral-800 z-50 flex flex-col justify-between transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full'
        }`}
      >
        {/* En-tête du menu */}
        <div className="p-4 border-b border-neutral-800 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 font-bold text-lg text-white">
              <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 animate-pulse"></span>
              <span>SensAI</span>
            </div>
            <button
              onClick={onClose}
              className="p-1 rounded-md text-neutral-400 hover:text-white hover:bg-neutral-800 cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Bouton "+ New conversation" tout en haut */}
          <div className="grid grid-cols-2 gap-2">
            <Button
              onClick={() => { onNewConversation('solo'); onClose(); }}
              className="w-full bg-indigo-600 hover:bg-indigo-500 text-white text-xs gap-1.5 cursor-pointer py-2"
            >
              <Plus className="w-4 h-4" />
              <span>Solo</span>
            </Button>
            <Button
              onClick={() => { onNewConversation('work'); onClose(); }}
              variant="outline"
              className="w-full border-neutral-700 bg-neutral-800/80 hover:bg-neutral-800 text-amber-300 text-xs gap-1.5 cursor-pointer py-2"
            >
              <Users className="w-4 h-4 text-amber-400" />
              <span>Work (Collab)</span>
            </Button>
          </div>

          {/* Recherche & Filtre des conversations */}
          <div className="space-y-2 pt-1">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-neutral-500 absolute left-2.5 top-2.5" />
              <Input
                placeholder="Rechercher..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 text-xs bg-neutral-950 border-neutral-800 h-8"
              />
            </div>

            <div className="flex items-center gap-1 text-[11px] bg-neutral-950 p-1 rounded-md border border-neutral-800">
              <button
                onClick={() => setFilterMode('all')}
                className={`flex-1 py-1 rounded cursor-pointer font-medium text-center ${
                  filterMode === 'all' ? 'bg-neutral-800 text-white' : 'text-neutral-400 hover:text-neutral-200'
                }`}
              >
                Toutes
              </button>
              <button
                onClick={() => setFilterMode('solo')}
                className={`flex-1 py-1 rounded cursor-pointer font-medium text-center ${
                  filterMode === 'solo' ? 'bg-neutral-800 text-indigo-300' : 'text-neutral-400 hover:text-neutral-200'
                }`}
              >
                Solo
              </button>
              <button
                onClick={() => setFilterMode('work')}
                className={`flex-1 py-1 rounded cursor-pointer font-medium text-center ${
                  filterMode === 'work' ? 'bg-neutral-800 text-amber-300' : 'text-neutral-400 hover:text-neutral-200'
                }`}
              >
                Work
              </button>
            </div>
          </div>
        </div>

        {/* Historique des conversations (scrollable) */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          <div className="px-2 pb-1 text-[11px] font-semibold tracking-wider text-neutral-500 uppercase">
            Historique ({filteredConversations.length})
          </div>

          {filteredConversations.length === 0 ? (
            <div className="text-center py-8 text-xs text-neutral-500">
              Aucune conversation trouvée
            </div>
          ) : (
            filteredConversations.map((conv) => {
              const isActive = conv.id === activeId
              return (
                <div
                  key={conv.id}
                  onClick={() => { onSelectConversation(conv.id); onClose(); }}
                  className={`group relative flex items-center justify-between p-2.5 rounded-lg text-xs cursor-pointer border transition-colors ${
                    isActive
                      ? 'bg-neutral-800/90 border-neutral-700 text-white shadow-xs'
                      : 'border-transparent text-neutral-300 hover:bg-neutral-800/50 hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0 pr-6">
                    {conv.mode === 'work' ? (
                      <Users className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                    ) : (
                      <MessageSquare className="w-3.5 h-3.5 text-neutral-400 shrink-0" />
                    )}
                    <span className="truncate font-medium">{conv.title}</span>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[10px] text-neutral-500 flex items-center gap-0.5">
                      <Coins className="w-2.5 h-2.5 text-amber-500/80" />
                      {conv.total_tokens || 0}
                    </span>

                    {/* Bouton suppression visible au survol */}
                    <button
                      onClick={(e) => onDeleteConversation(conv.id, e)}
                      title="Supprimer la conversation"
                      className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 text-neutral-500 cursor-pointer rounded transition-opacity"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Section Navigation & Profil (en bas) */}
        <div className="p-3 border-t border-neutral-800 space-y-2 bg-neutral-950/60">
          <div className="space-y-1">
            <button
              onClick={() => { onOpenModels(); onClose(); }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-xs text-neutral-300 hover:text-white hover:bg-neutral-800/70 cursor-pointer transition-colors"
            >
              <Cpu className="w-4 h-4 text-indigo-400" />
              <span>Modèles &amp; Tools</span>
            </button>

            <button
              onClick={() => { onOpenSettings(); onClose(); }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-xs text-neutral-300 hover:text-white hover:bg-neutral-800/70 cursor-pointer transition-colors"
            >
              <Settings className="w-4 h-4 text-neutral-400" />
              <span>Paramètres</span>
            </button>

            <button
              onClick={() => { onOpenMcp(); onClose(); }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-xs text-neutral-300 hover:text-white hover:bg-neutral-800/70 cursor-pointer transition-colors"
            >
              <Plug className="w-4 h-4 text-emerald-400" />
              <span>Intégrations MCP</span>
              <Badge variant="outline" className="ml-auto text-[9px] px-1 py-0 border-neutral-700 text-neutral-400">
                Futur
              </Badge>
            </button>
          </div>

          {/* En bas à droite : Nom d'utilisateur connecté et déconnexion */}
          <div className="pt-2 border-t border-neutral-800/80 flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-7 h-7 rounded-full bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-300 font-semibold text-xs shrink-0">
                {user.username.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-neutral-100 truncate">
                  {user.username}
                </div>
                <div className="text-[10px] text-emerald-400 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                  En ligne
                </div>
              </div>
            </div>

            <button
              onClick={onLogout}
              title="Se déconnecter"
              className="p-1.5 text-neutral-400 hover:text-red-400 hover:bg-neutral-800 rounded-md cursor-pointer transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}

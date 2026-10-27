import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { User, Lock, Plug, Plus, ShieldCheck, CheckCircle2, AlertCircle, Trash2, Power, PowerOff, Loader2, Wrench } from 'lucide-react'
import { api } from '../lib/api'
import type { McpServer, User as UserType } from '../types'

interface SettingsModalProps {
  isOpen: boolean
  onClose: () => void
  user: UserType
  onUserUpdated: (user: UserType) => void
  initialTab?: 'profile' | 'mcp'
}

export function SettingsModal({ isOpen, onClose, user, onUserUpdated, initialTab = 'profile' }: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState(initialTab)

  // Profil
  const [username, setUsername] = useState(user.username)
  const [newPassword, setNewPassword] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [loadingProfile, setLoadingProfile] = useState(false)

  // MCP
  const [mcpServers, setMcpServers] = useState<McpServer[]>([])
  const [newMcpName, setNewMcpName] = useState('')
  const [newMcpEndpoint, setNewMcpEndpoint] = useState('')
  const [newMcpDesc, setNewMcpDesc] = useState('')
  const [mcpLoading, setMcpLoading] = useState(false)
  const [mcpStatusMsg, setMcpStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [connectingServerId, setConnectingServerId] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen) {
      if (initialTab) {
        setActiveTab(initialTab)
      }
      setUsername(user.username)
      setStatusMsg(null)
      setMcpStatusMsg(null)
      loadMcpServers()
    }
  }, [isOpen, initialTab, user])

  const loadMcpServers = async () => {
    try {
      const res = await api.getMcpServers()
      setMcpServers(res.servers)
    } catch {
      // ignore
    }
  }

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    setStatusMsg(null)
    setLoadingProfile(true)

    try {
      const res = await api.updateSettings({
        username: username !== user.username ? username : undefined,
        new_password: newPassword ? newPassword : undefined,
        current_password: currentPassword,
      })
      onUserUpdated(res.user)
      setStatusMsg({ type: 'success', text: 'Paramètres mis à jour avec succès.' })
      setCurrentPassword('')
      setNewPassword('')
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message || 'Erreur lors de la mise à jour.' })
    } finally {
      setLoadingProfile(false)
    }
  }

  const handleAddMcp = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newMcpName || !newMcpEndpoint) return
    setMcpLoading(true)
    setMcpStatusMsg(null)
    try {
      const res = await api.addMcpServer({
        name: newMcpName,
        endpoint: newMcpEndpoint,
        description: newMcpDesc.trim() || undefined,
      })
      setMcpServers((prev) => [...prev, res.server])
      setNewMcpName('')
      setNewMcpEndpoint('')
      setNewMcpDesc('')
      setMcpStatusMsg({ type: 'success', text: `Serveur "${res.server.name}" ajouté avec succès.` })
    } catch (err: any) {
      setMcpStatusMsg({ type: 'error', text: err.message || "Erreur lors de l'ajout du serveur MCP." })
    } finally {
      setMcpLoading(false)
    }
  }

  const handleConnectMcp = async (serverId: string, serverName: string) => {
    setConnectingServerId(serverId)
    setMcpStatusMsg(null)
    try {
      const res = await api.connectMcpServer({ server_id: serverId })
      setMcpServers((prev) =>
        prev.map((s) =>
          s.id === serverId
            ? {
                ...s,
                ...res.server,
                status: 'connected',
                tools_count: res.tools_count,
                tools: res.tools,
              }
            : s
        )
      )
      setMcpStatusMsg({
        type: 'success',
        text: `Serveur "${serverName}" connecté (${res.tools_count} outil(s) découvert(s)).`,
      })
    } catch (err: any) {
      setMcpStatusMsg({
        type: 'error',
        text: err.message || `Erreur de connexion au serveur "${serverName}".`,
      })
    } finally {
      setConnectingServerId(null)
    }
  }

  const handleDisconnectMcp = async (serverId: string, serverName: string) => {
    setConnectingServerId(serverId)
    setMcpStatusMsg(null)
    try {
      await api.disconnectMcpServer(serverId)
      setMcpServers((prev) =>
        prev.map((s) =>
          s.id === serverId
            ? {
                ...s,
                status: 'disconnected',
                tools_count: 0,
                tools: [],
              }
            : s
        )
      )
      setMcpStatusMsg({
        type: 'success',
        text: `Serveur "${serverName}" déconnecté.`,
      })
    } catch (err: any) {
      setMcpStatusMsg({
        type: 'error',
        text: err.message || `Erreur de déconnexion du serveur "${serverName}".`,
      })
    } finally {
      setConnectingServerId(null)
    }
  }

  const handleDeleteMcp = async (serverId: string, serverName: string) => {
    try {
      await api.deleteMcpServer(serverId)
      setMcpServers((prev) => prev.filter((s) => s.id !== serverId))
      setMcpStatusMsg({ type: 'success', text: `Serveur "${serverName}" supprimé avec succès.` })
    } catch (err: any) {
      setMcpStatusMsg({ type: 'error', text: err.message || 'Erreur lors de la suppression du serveur MCP.' })
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-xl md:max-w-2xl bg-neutral-900 border-neutral-800 text-neutral-100 p-0 overflow-hidden">
        <DialogHeader className="p-5 border-b border-neutral-800 pb-4">
          <DialogTitle className="text-lg font-bold flex items-center gap-2">
            <span>Paramètres de la plateforme</span>
          </DialogTitle>
          <DialogDescription className="text-neutral-400 text-xs">
            Gérez vos informations de compte et préparez vos intégrations MCP.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <div className="px-5 border-b border-neutral-800 bg-neutral-950/40">
            <TabsList className="bg-transparent border-0 gap-4 p-0 h-10">
              <TabsTrigger
                value="profile"
                className="data-[state=active]:border-b-2 data-[state=active]:border-indigo-500 rounded-none bg-transparent text-xs text-neutral-400 data-[state=active]:text-white font-medium cursor-pointer"
              >
                Mon Compte &amp; Sécurité
              </TabsTrigger>
              <TabsTrigger
                value="mcp"
                className="data-[state=active]:border-b-2 data-[state=active]:border-emerald-500 rounded-none bg-transparent text-xs text-neutral-400 data-[state=active]:text-white font-medium cursor-pointer"
              >
                Intégrations MCP
              </TabsTrigger>
            </TabsList>
          </div>

          {/* Onglet Profil */}
          <TabsContent value="profile" className="p-5 space-y-4 m-0">
            {statusMsg && (
              <div
                className={`p-3 rounded-lg text-xs flex items-center gap-2 border ${
                  statusMsg.type === 'success'
                    ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
                    : 'bg-red-950/40 border-red-800 text-red-300'
                }`}
              >
                {statusMsg.type === 'success' ? (
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                ) : (
                  <AlertCircle className="w-4 h-4 shrink-0" />
                )}
                <span>{statusMsg.text}</span>
              </div>
            )}

            <form onSubmit={handleUpdateProfile} className="space-y-4">
              <div className="space-y-2">
                <Label className="text-xs text-neutral-300 flex items-center gap-1.5">
                  <User className="w-3.5 h-3.5 text-neutral-400" />
                  Nom d'utilisateur
                </Label>
                <Input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="bg-neutral-950 border-neutral-800 text-xs"
                  required
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label className="text-xs text-neutral-300 flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5 text-neutral-400" />
                    Nouveau mot de passe
                  </Label>
                  <Input
                    type="password"
                    placeholder="Laisser vide pour ne pas changer"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="bg-neutral-950 border-neutral-800 text-xs"
                  />
                </div>

                <div className="space-y-2">
                  <Label className="text-xs text-neutral-300 flex items-center gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
                    Mot de passe actuel *
                  </Label>
                  <Input
                    type="password"
                    placeholder="Obligatoire pour valider"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="bg-neutral-950 border-neutral-800 text-xs"
                    required
                  />
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  type="submit"
                  disabled={loadingProfile}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs cursor-pointer"
                >
                  {loadingProfile ? 'Mise à jour...' : 'Sauvegarder les modifications'}
                </Button>
              </div>
            </form>
          </TabsContent>

          {/* Onglet MCP (Model Context Protocol) */}
          <TabsContent value="mcp" className="p-5 space-y-4 m-0">
            {mcpStatusMsg && (
              <div
                className={`p-3 rounded-lg text-xs flex items-center gap-2 border ${
                  mcpStatusMsg.type === 'success'
                    ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
                    : 'bg-red-950/40 border-red-800 text-red-300'
                }`}
              >
                {mcpStatusMsg.type === 'success' ? (
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                ) : (
                  <AlertCircle className="w-4 h-4 shrink-0" />
                )}
                <span>{mcpStatusMsg.text}</span>
              </div>
            )}

            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Plug className="w-4 h-4 text-emerald-400" />
                <h4 className="text-sm font-semibold text-white">Serveurs MCP Connectés</h4>
              </div>
              <p className="text-xs text-neutral-400">
                Préparez et intégrez des serveurs MCP pour injecter des capacités externes (fichiers, bases de données, APIs tierces).
              </p>
            </div>

            <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
              {mcpServers.length === 0 ? (
                <div className="p-4 text-center text-xs text-neutral-500 border border-dashed border-neutral-800 rounded-lg">
                  Aucun serveur MCP configuré pour le moment.
                </div>
              ) : (
                mcpServers.map((srv) => (
                  <div
                    key={srv.id}
                    className="p-3 rounded-lg border border-neutral-800 bg-neutral-950/60 flex items-start justify-between gap-3 text-xs"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold text-neutral-100 flex items-center gap-2 flex-wrap">
                        <span>{srv.name}</span>
                        <span className="text-[10px] text-neutral-500 font-mono">({srv.endpoint})</span>
                        {typeof srv.tools_count === 'number' && srv.tools_count > 0 && (
                          <Badge variant="outline" className="text-[9px] px-1.5 py-0 border-emerald-900/60 bg-emerald-950/30 text-emerald-300">
                            {srv.tools_count} outil{srv.tools_count > 1 ? 's' : ''} actif{srv.tools_count > 1 ? 's' : ''}
                          </Badge>
                        )}
                      </div>
                      <div className="text-[11px] text-neutral-400 leading-relaxed break-words mt-1">
                        {srv.description}
                      </div>

                      {/* Outils découverts en cas de connexion active */}
                      {srv.status === 'connected' && srv.tools && srv.tools.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-neutral-800/60 flex flex-wrap gap-1.5 items-center">
                          <span className="text-[10px] text-neutral-500 mr-1 flex items-center gap-1">
                            <Wrench className="w-2.5 h-2.5" />
                            Outils découverts :
                          </span>
                          {srv.tools.map((tName) => (
                            <Badge
                              key={tName}
                              variant="outline"
                              className="text-[9px] px-1.5 py-0 border-zinc-800 bg-zinc-900/80 text-zinc-300 font-mono"
                            >
                              {tName}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0 pt-0.5">
                      <Badge
                        variant="outline"
                        className={`text-[10px] capitalize ${
                          srv.status === 'connected'
                            ? 'border-emerald-800 text-emerald-400 bg-emerald-950/40'
                            : srv.status === 'available'
                            ? 'border-sky-800 text-sky-400 bg-sky-950/40'
                            : 'border-neutral-700 text-neutral-400'
                        }`}
                      >
                        {srv.status === 'connected' ? 'Connecté' : srv.status === 'available' ? 'Disponible' : srv.status === 'disconnected' ? 'Déconnecté' : srv.status}
                      </Badge>

                      {srv.status === 'connected' ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={connectingServerId === srv.id}
                          onClick={() => handleDisconnectMcp(srv.id, srv.name)}
                          className="h-6 px-2 text-[10px] border-neutral-800 text-neutral-400 hover:text-red-400 hover:border-red-900/50 cursor-pointer"
                          title="Déconnecter ce serveur MCP"
                        >
                          {connectingServerId === srv.id ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <>
                              <PowerOff className="w-3 h-3 mr-1" />
                              Déconnecter
                            </>
                          )}
                        </Button>
                      ) : (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={connectingServerId === srv.id}
                          onClick={() => handleConnectMcp(srv.id, srv.name)}
                          className="h-6 px-2 text-[10px] border-neutral-800 text-neutral-300 hover:text-emerald-400 hover:border-emerald-900/50 cursor-pointer"
                          title="Connecter ce serveur MCP"
                        >
                          {connectingServerId === srv.id ? (
                            <>
                              <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                              Connexion...
                            </>
                          ) : (
                            <>
                              <Power className="w-3 h-3 mr-1" />
                              Connecter
                            </>
                          )}
                        </Button>
                      )}

                      <button
                        type="button"
                        onClick={() => handleDeleteMcp(srv.id, srv.name)}
                        className="p-1 rounded text-neutral-500 hover:text-red-400 hover:bg-neutral-900 transition-colors cursor-pointer"
                        title="Supprimer ce serveur"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="p-3 rounded-lg border border-neutral-800 bg-neutral-950/40 space-y-3">
              <div className="text-xs font-semibold text-neutral-200">Ajouter un nouveau serveur MCP</div>
              <form onSubmit={handleAddMcp} className="space-y-2">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <Input
                    placeholder="Nom (ex: Warring States DB)"
                    value={newMcpName}
                    onChange={(e) => setNewMcpName(e.target.value)}
                    className="text-xs bg-neutral-950 border-neutral-800 h-8"
                  />
                  <Input
                    placeholder="Endpoint / Commande (ex: python -m src...)"
                    value={newMcpEndpoint}
                    onChange={(e) => setNewMcpEndpoint(e.target.value)}
                    className="text-xs bg-neutral-950 border-neutral-800 h-8"
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-5 gap-2">
                  <Input
                    placeholder="Description (optionnel)"
                    value={newMcpDesc}
                    onChange={(e) => setNewMcpDesc(e.target.value)}
                    className="sm:col-span-4 text-xs bg-neutral-950 border-neutral-800 h-8"
                  />
                  <Button
                    type="submit"
                    disabled={mcpLoading || !newMcpName || !newMcpEndpoint}
                    className="sm:col-span-1 h-8 text-xs bg-emerald-600 hover:bg-emerald-500 text-white cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5 mr-1" />
                    Ajouter
                  </Button>
                </div>
              </form>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

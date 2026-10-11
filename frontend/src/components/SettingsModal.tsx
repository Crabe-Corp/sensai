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
import { User, Lock, Plug, Plus, ShieldCheck, CheckCircle2, AlertCircle } from 'lucide-react'
import { api } from '../lib/api'
import type { McpServer, User as UserType } from '../types'

interface SettingsModalProps {
  isOpen: boolean
  onClose: () => void
  user: UserType
  onUserUpdated: (user: UserType) => void
}

export function SettingsModal({ isOpen, onClose, user, onUserUpdated }: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState('profile')

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
  const [mcpLoading, setMcpLoading] = useState(false)

  useEffect(() => {
    if (isOpen) {
      setUsername(user.username)
      setStatusMsg(null)
      loadMcpServers()
    }
  }, [isOpen, user])

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
    try {
      const res = await api.addMcpServer({
        name: newMcpName,
        endpoint: newMcpEndpoint,
      })
      setMcpServers((prev) => [...prev, res.server])
      setNewMcpName('')
      setNewMcpEndpoint('')
    } catch {
      // ignore
    } finally {
      setMcpLoading(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-xl bg-neutral-900 border-neutral-800 text-neutral-100 p-0 overflow-hidden">
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
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Plug className="w-4 h-4 text-emerald-400" />
                <h4 className="text-sm font-semibold text-white">Serveurs MCP Connectés</h4>
              </div>
              <p className="text-xs text-neutral-400">
                Préparez et intégrez des serveurs MCP pour injecter des capacités externes (fichiers, bases de données, APIs tierces).
              </p>
            </div>

            <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
              {mcpServers.map((srv) => (
                <div
                  key={srv.id}
                  className="p-3 rounded-lg border border-neutral-800 bg-neutral-950/60 flex items-center justify-between gap-3 text-xs"
                >
                  <div className="min-w-0">
                    <div className="font-semibold text-neutral-100 flex items-center gap-2">
                      <span>{srv.name}</span>
                      <span className="text-[10px] text-neutral-500 font-mono">({srv.endpoint})</span>
                    </div>
                    <div className="text-[11px] text-neutral-400 truncate">{srv.description}</div>
                  </div>

                  <Badge
                    variant="outline"
                    className={`text-[10px] capitalize shrink-0 ${
                      srv.status === 'connected'
                        ? 'border-emerald-800 text-emerald-400 bg-emerald-950/40'
                        : 'border-neutral-700 text-neutral-400'
                    }`}
                  >
                    {srv.status === 'connected' ? 'Connecté' : srv.status}
                  </Badge>
                </div>
              ))}
            </div>

            <div className="p-3 rounded-lg border border-neutral-800 bg-neutral-950/40 space-y-3">
              <div className="text-xs font-semibold text-neutral-200">Ajouter un nouveau serveur MCP</div>
              <form onSubmit={handleAddMcp} className="grid grid-cols-1 sm:grid-cols-5 gap-2">
                <Input
                  placeholder="Nom (ex: Mon_Outil)"
                  value={newMcpName}
                  onChange={(e) => setNewMcpName(e.target.value)}
                  className="sm:col-span-2 text-xs bg-neutral-950 border-neutral-800 h-8"
                />
                <Input
                  placeholder="Endpoint / URI"
                  value={newMcpEndpoint}
                  onChange={(e) => setNewMcpEndpoint(e.target.value)}
                  className="sm:col-span-2 text-xs bg-neutral-950 border-neutral-800 h-8"
                />
                <Button
                  type="submit"
                  disabled={mcpLoading || !newMcpName || !newMcpEndpoint}
                  className="sm:col-span-1 h-8 text-xs bg-emerald-600 hover:bg-emerald-500 text-white cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5 mr-1" />
                  Ajouter
                </Button>
              </form>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

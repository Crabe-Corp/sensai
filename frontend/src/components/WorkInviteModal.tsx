import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Users, UserPlus, CheckCircle2, AlertCircle } from 'lucide-react'
import { api } from '../lib/api'

interface WorkInviteModalProps {
  isOpen: boolean
  onClose: () => void
  conversationId: string | null
  onMemberAdded?: () => void
}

export function WorkInviteModal({
  isOpen,
  onClose,
  conversationId,
  onMemberAdded,
}: WorkInviteModalProps) {
  const [username, setUsername] = useState('')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!conversationId || !username.trim()) return

    setLoading(true)
    setMsg(null)
    try {
      const res = await api.addMember(conversationId, username.trim(), 'editor')
      setMsg({ type: 'success', text: res.message || 'Membre ajouté avec succès' })
      setUsername('')
      onMemberAdded?.()
    } catch (err: any) {
      setMsg({ type: 'error', text: err.message || "Erreur lors de l'ajout" })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-md bg-neutral-900 border-neutral-800 text-neutral-100 p-5 space-y-4">
        <DialogHeader className="pb-2 border-b border-neutral-800">
          <DialogTitle className="text-base font-bold flex items-center gap-2">
            <Users className="w-5 h-5 text-amber-400" />
            <span>Collaboration "Work" en temps réel</span>
          </DialogTitle>
          <DialogDescription className="text-neutral-400 text-xs">
            Ajoutez un utilisateur par son nom pour lui donner accès à cette conversation. Tous les participants voient les échanges en direct !
          </DialogDescription>
        </DialogHeader>

        {msg && (
          <div
            className={`p-3 rounded-lg text-xs flex items-center gap-2 border ${
              msg.type === 'success'
                ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
                : 'bg-red-950/40 border-red-800 text-red-300'
            }`}
          >
            {msg.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 shrink-0" />
            )}
            <span>{msg.text}</span>
          </div>
        )}

        <form onSubmit={handleInvite} className="space-y-4">
          <div className="space-y-2">
            <Label className="text-xs text-neutral-300">Nom d'utilisateur du collaborateur</Label>
            <Input
              placeholder="Ex: ArthurPendragon"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              className="bg-neutral-950 border-neutral-800 text-xs"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onClose}
              className="text-xs border-neutral-800 bg-neutral-900 text-neutral-300 cursor-pointer"
            >
              Fermer
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={loading || !username.trim()}
              className="text-xs bg-amber-600 hover:bg-amber-500 text-white cursor-pointer gap-1.5"
            >
              <UserPlus className="w-4 h-4" />
              <span>{loading ? 'Ajout...' : 'Inviter'}</span>
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}


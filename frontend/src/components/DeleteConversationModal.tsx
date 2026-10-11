import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Trash2 } from 'lucide-react'

interface DeleteConversationModalProps {
  isOpen: boolean
  onClose: () => void
  conversationTitle?: string
  onConfirm: () => void
  isDeleting?: boolean
}

export function DeleteConversationModal({
  isOpen,
  onClose,
  conversationTitle = 'cette conversation',
  onConfirm,
  isDeleting = false,
}: DeleteConversationModalProps) {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md bg-neutral-900 border-neutral-800 text-neutral-100">
        <DialogHeader className="space-y-3">
          <div className="flex items-center gap-2.5 text-red-400">
            <div className="p-2 rounded-xl bg-red-950/60 border border-red-800/80">
              <Trash2 className="w-5 h-5 text-red-400" />
            </div>
            <DialogTitle className="text-base font-semibold text-white">
              Supprimer la conversation ?
            </DialogTitle>
          </div>
          <DialogDescription className="text-neutral-400 text-xs leading-relaxed">
            Êtes-vous sûr de vouloir supprimer définitivement{' '}
            <span className="font-semibold text-neutral-200">« {conversationTitle} »</span> ?
            Tous les messages de cet échange seront effacés. Cette action est irréversible.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-end gap-2.5 pt-3">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={isDeleting}
            className="text-xs text-neutral-400 hover:text-white hover:bg-neutral-800 cursor-pointer"
          >
            Annuler
          </Button>
          <Button
            type="button"
            onClick={onConfirm}
            disabled={isDeleting}
            className="text-xs bg-red-600 hover:bg-red-500 text-white gap-1.5 shadow-md cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>{isDeleting ? 'Suppression...' : 'Supprimer'}</span>
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}


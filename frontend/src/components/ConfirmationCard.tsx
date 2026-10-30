import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ShieldAlert, FilePen, DatabaseZap, Check, X } from 'lucide-react'
import type { ConfirmationSpec } from '../types'

interface ConfirmationCardProps {
  confirmation: ConfirmationSpec
  disabled: boolean
  onConfirm: (text: string) => void
  onReject: (text: string) => void
}

export function ConfirmationCard({
  confirmation,
  disabled,
  onConfirm,
  onReject,
}: ConfirmationCardProps) {
  const [responded, setResponded] = useState<'approved' | 'rejected' | null>(null)

  const isFile = confirmation.action_type === 'file_write'

  const handleConfirm = () => {
    if (disabled || responded) return
    setResponded('approved')
    const tokenPart = confirmation.action_id ? ` [action_id:${confirmation.action_id}]` : ''
    onConfirm(`[Confirmation : approuvée]${tokenPart} J'approuve l'exécution : ${confirmation.summary}`)
  }

  const handleReject = () => {
    if (disabled || responded) return
    setResponded('rejected')
    const tokenPart = confirmation.action_id ? ` [action_id:${confirmation.action_id}]` : ''
    onReject(`[Confirmation : refusée]${tokenPart} J'annule et refuse l'opération : ${confirmation.summary}`)
  }

  const getIcon = () => {    if (isDb) return <DatabaseZap className="w-3.5 h-3.5 text-zinc-300" />
    if (isFile) return <FilePen className="w-3.5 h-3.5 text-zinc-300" />
    return <ShieldAlert className="w-3.5 h-3.5 text-zinc-300" />
  }

  const getCategoryLabel = () => {
    if (isFile) return "Écriture manuscrit"
    return "Action critique"
  }

  return (
    <div
      className={`mt-2.5 p-3.5 rounded-lg border border-zinc-800 bg-[#0c0d0e] space-y-3 whitespace-normal shadow-sm transition-colors ${
        disabled && !responded ? 'opacity-60' : ''
      }`}
    >
      {/* En-tête sobre style Linear */}
      <div className="flex items-center justify-between gap-2 border-b border-zinc-800/80 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-zinc-900 border border-zinc-800 flex items-center justify-center">
            {getIcon()}
          </div>
          <span className="text-xs font-semibold text-zinc-200">
            Confirmation requise
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <Badge
            variant="outline"
            className="text-[10px] uppercase tracking-wider font-mono px-1.5 py-0 border-zinc-800 text-zinc-400 bg-zinc-900/60"
          >
            {getCategoryLabel()}
          </Badge>
          {confirmation.action_id && (
            <span className="text-[10px] font-mono text-zinc-500">
              #{confirmation.action_id}
            </span>
          )}
        </div>
      </div>

      {/* Description de l'action et conséquences */}
      <div className="text-xs leading-relaxed text-zinc-300">
        {confirmation.summary}
      </div>

      {/* Détails techniques optionnels */}
      {confirmation.details && typeof confirmation.details === 'object' && Object.keys(confirmation.details).length > 0 && (
        <div className="p-2 rounded-md bg-zinc-950 border border-zinc-800/80 text-[11px] font-mono text-zinc-400 overflow-x-auto">
          {confirmation.details.sql_statement && (
            <div>
              <span className="text-zinc-500 block mb-0.5">Instruction SQL :</span>
              <span className="text-zinc-200">{String(confirmation.details.sql_statement)}</span>
            </div>
          )}
          {confirmation.details.filename && (
            <div>
              <span className="text-zinc-500 block mb-0.5">Cible :</span>
              <span className="text-zinc-200">{String(confirmation.details.filename)}</span>
            </div>
          )}
        </div>
      )}

      {/* Actions de validation / refus */}
      <div className="flex items-center justify-between gap-2 pt-0.5">
        {responded ? (
          <div className="text-[11px] font-medium flex items-center gap-1.5 py-1">
            {responded === 'approved' ? (
              <span className="text-emerald-400 flex items-center gap-1">
                <Check className="w-3.5 h-3.5" /> Action approuvée
              </span>
            ) : (
              <span className="text-zinc-400 flex items-center gap-1">
                <X className="w-3.5 h-3.5" /> Action refusée
              </span>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              disabled={disabled}
              onClick={handleConfirm}
              className="h-7 px-3 text-xs font-medium bg-zinc-100 text-zinc-900 hover:bg-zinc-200 rounded-md transition-colors"
            >
              <Check className="w-3.5 h-3.5 mr-1" />
              Confirmer
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={disabled}
              onClick={handleReject}
              className="h-7 px-3 text-xs border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 rounded-md transition-colors"
            >
              <X className="w-3.5 h-3.5 mr-1" />
              Refuser
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

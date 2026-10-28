import { useState, useEffect } from 'react'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import type { ToolInfo, Persona } from '../types'
import { api } from '../lib/api'
import { ToolIcon } from './ToolIcon'
import {
  X,
  Cpu,
  Sparkles,
  Coins,
  ChevronDown,
  Wrench,
  User,
  Trash2,
} from 'lucide-react'

interface RunSettingsPanelProps {
  isOpen: boolean
  onClose: () => void
  model: string
  modelsList: string[]
  onModelChange: (model: string) => void
  toolsList: ToolInfo[]
  activeTools: string[]
  onToggleTool: (toolId: string) => void
  systemInstruction: string
  onSystemInstructionChange: (val: string) => void
  totalTokens: number
  personas?: Persona[]
  conversationId?: string
}

export function RunSettingsPanel({
  isOpen,
  onClose,
  model,
  modelsList,
  onModelChange,
  toolsList,
  activeTools,
  onToggleTool,
  systemInstruction,
  onSystemInstructionChange,
  totalTokens,
  personas: initialPersonas,
  conversationId,
}: RunSettingsPanelProps) {
  const [cacheClearing, setCacheClearing] = useState(false)
  const [cacheStatus, setCacheStatus] = useState<string | null>(null)

  const handleClearCache = async () => {
    if (!conversationId) return
    setCacheClearing(true)
    setCacheStatus(null)
    try {
      const res = await api.clearCache(conversationId)
      setCacheStatus(res.message || 'Cache vidé')
      setTimeout(() => setCacheStatus(null), 3000)
    } catch (err: any) {
      setCacheStatus(err.message || 'Erreur lors du vidage')
      setTimeout(() => setCacheStatus(null), 3000)
    } finally {
      setCacheClearing(false)
    }
  }
  const [toolsOpen, setToolsOpen] = useState(true)
  const [personas, setPersonas] = useState<Persona[]>(initialPersonas || [])
  const [selectedPersonaId, setSelectedPersonaId] = useState<string>('')

  useEffect(() => {
    let isMounted = true
    api.getPersonas()
      .then((data) => {
        if (isMounted && Array.isArray(data) && data.length > 0) {
          setPersonas(data)
        }
      })
      .catch(() => {
        // ignore
      })
    return () => {
      isMounted = false
    }
  }, [])

  useEffect(() => {
    if (initialPersonas && initialPersonas.length > 0) {
      setPersonas(initialPersonas)
    }
  }, [initialPersonas])

  // Détection de la persona correspondant aux instructions actuelles
  const matchedPersona = personas.find(
    (p) => p.system_prompt.trim() === systemInstruction.trim()
  )
  const effectivePersonaId = selectedPersonaId || (matchedPersona ? matchedPersona.id : '')
  const activePersona = personas.find((p) => p.id === effectivePersonaId)

  const handlePersonaSelect = (personaId: string) => {
    setSelectedPersonaId(personaId)
    if (!personaId) return
    const chosen = personas.find((p) => p.id === personaId)
    if (chosen) {
      onSystemInstructionChange(chosen.system_prompt)
    }
  }

  return (
    <aside
      className={`h-full border-l border-neutral-800 bg-neutral-900/95 backdrop-blur-md z-20 shrink-0 text-neutral-100 overflow-hidden transition-all duration-300 ease-in-out ${
        isOpen
          ? 'w-80 sm:w-88 opacity-100 translate-x-0'
          : 'w-0 opacity-0 translate-x-full border-l-0 pointer-events-none'
      }`}
    >
      <div className="w-80 sm:w-88 min-w-[20rem] sm:min-w-[22rem] h-full flex flex-col justify-between overflow-y-auto">
        {/* Header façon Google AI Studio */}
        <div className="p-4 border-b border-neutral-800 flex items-center justify-between sticky top-0 bg-neutral-900/95 z-10">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold tracking-wide text-neutral-300">
              Run settings
            </span>
            <Badge variant="outline" className="text-[10px] border-neutral-700 text-neutral-400 px-1 py-0">
              AI Studio style
            </Badge>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-neutral-400 hover:text-white hover:bg-neutral-800 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-6 flex-1">
          {/* Sélecteur de Modèle */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold text-neutral-200">
              <span className="flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-indigo-400" />
                Modèle
              </span>
              <span className="text-[10px] text-emerald-400 font-mono">Ollama Local</span>
            </div>

            <div className="p-3 rounded-xl border border-neutral-800 bg-neutral-950/60 space-y-2">
              <select
                value={model}
                onChange={(e) => onModelChange(e.target.value)}
                className="w-full bg-neutral-900 border border-neutral-700/80 rounded-lg p-2 text-xs text-white focus:outline-none focus:border-indigo-500 cursor-pointer"
              >
                {modelsList.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <p className="text-[11px] text-neutral-400 leading-relaxed">
                Modèle d'inférence haute performance, optimisé pour les réponses fluides et l'appel d'outils.
              </p>
            </div>
          </div>

          {/* Sélecteur sobre de Persona (rôle IA) */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold text-neutral-200">
              <span className="flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-indigo-400" />
                Persona
              </span>
              <span className="text-[10px] text-neutral-500">Rôle IA</span>
            </div>

            <div className="p-3 rounded-xl border border-neutral-800 bg-neutral-950/60 space-y-2">
              <select
                value={effectivePersonaId}
                onChange={(e) => handlePersonaSelect(e.target.value)}
                className="w-full bg-neutral-900 border border-neutral-700/80 rounded-lg p-2 text-xs text-white focus:outline-none focus:border-indigo-500 cursor-pointer"
              >
                <option value="">Standard (Par défaut)</option>
                {personas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              {activePersona?.description ? (
                <p className="text-[11px] text-neutral-400 leading-relaxed">
                  {activePersona.description}
                </p>
              ) : (
                <p className="text-[11px] text-neutral-500 leading-relaxed">
                  Incarne un rôle spécifique (ex: Empereur, Général, Stratège, Espion).
                </p>
              )}
            </div>
          </div>

          {/* System Instructions (comme Google AI Studio) */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold text-neutral-200">
              <span className="flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                System instructions
              </span>
              <span className="text-[10px] text-neutral-500">Optionnel</span>
            </div>
            <Textarea
              value={systemInstruction}
              onChange={(e) => {
                setSelectedPersonaId('')
                onSystemInstructionChange(e.target.value)
              }}
              placeholder="Instructions de ton et de style pour le modèle (ex: Tu réponds de façon claire, synthétique et précise...)"
              rows={3}
              className="text-xs bg-neutral-950 border-neutral-800 text-neutral-200 resize-none rounded-xl placeholder:text-neutral-500 focus:border-indigo-500"
            />
          </div>

          {/* Section Tools avec liste de switches (exactement comme Google AI Studio) */}
          <div className="space-y-3">
            <button
              type="button"
              onClick={() => setToolsOpen(!toolsOpen)}
              className="w-full flex items-center justify-between text-xs font-semibold text-neutral-200 cursor-pointer"
            >
              <span className="flex items-center gap-1.5">
                <Wrench className="w-3.5 h-3.5 text-indigo-400" />
                Tools
              </span>
              <ChevronDown
                className={`w-3.5 h-3.5 text-neutral-400 transition-transform ${
                  toolsOpen ? 'rotate-180' : ''
                }`}
              />
            </button>

            {toolsOpen && (
              <div className="space-y-2.5 pt-1">
                {/* Tool 1 : Structured Output */}
                <button
                  type="button"
                  onClick={() => onToggleTool('structured_output')}
                  className="w-full text-left p-3 rounded-xl border border-neutral-800 bg-neutral-950/40 hover:bg-neutral-900/60 transition-colors flex items-start justify-between gap-3 cursor-pointer"
                >
                  <div className="space-y-1 min-w-0 flex-1">
                    <div className="text-xs font-medium text-neutral-200 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                      <span>Structured Output</span>
                    </div>
                    <div className="text-[11px] text-neutral-400 leading-relaxed break-words">
                      Formate et génère une sortie au format JSON structuré strict.
                    </div>
                    <div className="text-[10px] text-neutral-500">
                      Source: <span className="text-neutral-400">Sortie JSON structurée</span>
                    </div>
                  </div>
                  <Switch
                    checked={activeTools.includes('structured_output') || activeTools.includes('Structured Output')}
                    tabIndex={-1}
                    className="shrink-0 pointer-events-none mt-0.5"
                  />
                </button>

                {/* Outils du registre partagé avec le CLI (web_search, base des royaumes, RAG...) */}
                {toolsList
                  .filter((tool) => tool.id !== 'structured_output' && tool.visible !== false)
                  .map((tool) => (
                    <button
                      type="button"
                      key={tool.id}
                      onClick={() => onToggleTool(tool.id)}
                      className="w-full text-left p-3 rounded-xl border border-neutral-800 bg-neutral-950/40 hover:bg-neutral-900/60 transition-colors flex items-start justify-between gap-3 cursor-pointer"
                    >
                      <div className="space-y-1 min-w-0 flex-1">
                        <div className="text-xs font-medium text-neutral-200 flex items-center gap-1.5">
                          <ToolIcon name={tool.icon} className="w-3.5 h-3.5 shrink-0" />
                          <span className="truncate">{tool.name}</span>
                        </div>
                        {tool.description && (
                          <div className="text-[11px] text-neutral-400 leading-relaxed break-words">
                            {tool.description}
                          </div>
                        )}
                        <div className="text-[10px] text-neutral-500">
                          Source: <span className="text-neutral-400">{tool.category}</span>
                        </div>
                      </div>
                      <Switch
                        checked={activeTools.includes(tool.id)}
                        tabIndex={-1}
                        className="shrink-0 pointer-events-none mt-0.5"
                      />
                    </button>
                  ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer statistiques de Tokens & Actions */}
        <div className="p-4 border-t border-neutral-800 bg-neutral-950/80 sticky bottom-0 space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-neutral-400 flex items-center gap-1.5">
              <Coins className="w-3.5 h-3.5 text-amber-400" />
              Tokens session :
            </span>
            <span className="font-bold text-amber-300 font-mono">{totalTokens}</span>
          </div>

          {conversationId && (
            <button
              type="button"
              onClick={handleClearCache}
              disabled={cacheClearing}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs text-neutral-400 hover:text-neutral-200 bg-neutral-900 hover:bg-neutral-850 border border-neutral-800 rounded-md transition-colors cursor-pointer disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5 text-neutral-500" />
              <span>{cacheClearing ? 'Purge du cache...' : cacheStatus || 'Vider le cache sémantique'}</span>
            </button>
          )}
        </div>
      </div>
    </aside>
  )
}

import { useState } from 'react'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import {
  X,
  Cpu,
  Sparkles,
  Plug,
  Coins,
  ChevronDown,
  Wrench,
} from 'lucide-react'

interface RunSettingsPanelProps {
  isOpen: boolean
  onClose: () => void
  model: string
  modelsList: string[]
  onModelChange: (model: string) => void
  activeTools: string[]
  onToggleTool: (toolId: string) => void
  systemInstruction: string
  onSystemInstructionChange: (val: string) => void
  totalTokens: number
}

export function RunSettingsPanel({
  isOpen,
  onClose,
  model,
  modelsList,
  onModelChange,
  activeTools,
  onToggleTool,
  systemInstruction,
  onSystemInstructionChange,
  totalTokens,
}: RunSettingsPanelProps) {
  const [toolsOpen, setToolsOpen] = useState(true)

  if (!isOpen) return null

  return (
    <aside className="w-80 sm:w-88 border-l border-neutral-800 bg-neutral-900/95 backdrop-blur-md h-full flex flex-col justify-between z-20 shrink-0 text-neutral-100 overflow-y-auto">
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
            onChange={(e) => onSystemInstructionChange(e.target.value)}
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
                <div className="space-y-1 min-w-0">
                  <div className="text-xs font-medium text-neutral-200 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                    <span>Structured Output</span>
                  </div>
                  <div className="text-[10px] text-neutral-500">
                    Source: <span className="text-neutral-400">Sortie JSON structurée</span>
                  </div>
                </div>
                <Switch
                  checked={activeTools.includes('structured_output') || activeTools.includes('Structured Output')}
                  tabIndex={-1}
                  className="shrink-0 pointer-events-none"
                />
              </button>

              {/* Tool 2 : MCP */}
              <button
                type="button"
                onClick={() => onToggleTool('mcp_runner')}
                className="w-full text-left p-3 rounded-xl border border-neutral-800 bg-neutral-950/40 hover:bg-neutral-900/60 transition-colors flex items-start justify-between gap-3 cursor-pointer"
              >
                <div className="space-y-1 min-w-0">
                  <div className="text-xs font-medium text-neutral-200 flex items-center gap-1.5">
                    <Plug className="w-3.5 h-3.5 text-sky-400 shrink-0" />
                    <span>Intégrations MCP</span>
                  </div>
                  <div className="text-[10px] text-neutral-500">
                    Source: <span className="text-neutral-400">shadcn / Composio</span>
                  </div>
                </div>
                <Switch
                  checked={activeTools.includes('mcp_runner')}
                  tabIndex={-1}
                  className="shrink-0 pointer-events-none"
                />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Footer statistiques de Tokens façon Google AI Studio */}
      <div className="p-4 border-t border-neutral-800 bg-neutral-950/80 sticky bottom-0">
        <div className="flex items-center justify-between text-xs">
          <span className="text-neutral-400 flex items-center gap-1.5">
            <Coins className="w-3.5 h-3.5 text-amber-400" />
            Tokens session :
          </span>
          <span className="font-bold text-amber-300 font-mono">{totalTokens}</span>
        </div>
      </div>
    </aside>
  )
}

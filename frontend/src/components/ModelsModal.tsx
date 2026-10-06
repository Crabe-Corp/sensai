import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Cpu, Wrench, Check, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import type { ToolInfo } from '../types'

interface ModelsModalProps {
  isOpen: boolean
  onClose: () => void
  currentModel: string
  activeTools: string[]
  onModelChanged: (model: string) => void
  onToolsChanged: (tools: string[]) => void
}

export function ModelsModal({
  isOpen,
  onClose,
  currentModel,
  activeTools,
  onModelChanged,
  onToolsChanged,
}: ModelsModalProps) {
  const [models, setModels] = useState<string[]>([])
  const [selectedModel, setSelectedModel] = useState(currentModel)
  const [toolsList, setToolsList] = useState<ToolInfo[]>([])
  const [selectedTools, setSelectedTools] = useState<string[]>(activeTools)
  const [saving, setSaving] = useState(false)
  const [savedSuccess, setSavedSuccess] = useState(false)

  useEffect(() => {
    if (isOpen) {
      setSelectedModel(currentModel)
      setSelectedTools(activeTools)
      setSavedSuccess(false)
      loadData()
    }
  }, [isOpen, currentModel, activeTools])

  const loadData = async () => {
    try {
      const [modelsRes, toolsRes] = await Promise.all([api.getModels(), api.getTools()])
      setModels(modelsRes.models || ['qwen3:0.6b'])
      setToolsList(toolsRes || [])
    } catch {
      // ignore
    }
  }

  const handleToggleTool = (toolId: string) => {
    setSelectedTools((prev) =>
      prev.includes(toolId) ? prev.filter((id) => id !== toolId) : [...prev, toolId]
    )
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.saveModelConfig({
        model_name: selectedModel,
        active_tools: selectedTools,
      })
      onModelChanged(selectedModel)
      onToolsChanged(selectedTools)
      setSavedSuccess(true)
      setTimeout(() => {
        onClose()
      }, 700)
    } catch {
      // ignore
    } finally {
      setSaving(false)
    }
  }

  const getToolIcon = (iconName: string) => {
    switch (iconName) {
      case 'Code':
      case 'Sparkles':
        return <Sparkles className="w-4 h-4 text-indigo-400" />
      default:
        return <Wrench className="w-4 h-4 text-neutral-400" />
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-xl bg-neutral-900 border-neutral-800 text-neutral-100 p-5 space-y-4">
        <DialogHeader className="pb-3 border-b border-neutral-800">
          <DialogTitle className="text-lg font-bold flex items-center gap-2">
            <Cpu className="w-5 h-5 text-indigo-400" />
            <span>Configuration du Modèle &amp; Tools</span>
          </DialogTitle>
          <DialogDescription className="text-neutral-400 text-xs">
            Choisissez votre modèle d'IA et configurez les outils intégrés.
          </DialogDescription>
        </DialogHeader>

        {/* Sélection du modèle */}
        <div className="space-y-2">
          <div className="text-xs font-semibold text-neutral-200 flex items-center justify-between">
            <span>Modèle d'inférence (Ollama)</span>
            <Badge variant="outline" className="text-[10px] border-neutral-700 text-neutral-400">
              Local
            </Badge>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {models.map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setSelectedModel(m)}
                className={`p-3 rounded-lg border text-left text-xs transition-colors cursor-pointer flex items-center justify-between ${
                  selectedModel === m
                    ? 'bg-indigo-950/60 border-indigo-600 text-white shadow-xs'
                    : 'bg-neutral-950 border-neutral-800 text-neutral-300 hover:border-neutral-700'
                }`}
              >
                <div>
                  <div className="font-semibold">{m}</div>
                  <div className="text-[10px] text-neutral-400">Prêt pour l'inférence</div>
                </div>
                {selectedModel === m && <Check className="w-4 h-4 text-indigo-400" />}
              </button>
            ))}
          </div>
        </div>

        {/* Section Tools faits main dans le repo */}
        <div className="space-y-3 pt-2">
          <div className="text-xs font-semibold text-neutral-200 flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>Tools intégrés (Repo)</span>
          </div>
          <p className="text-[11px] text-neutral-400">
            Ces outils permettent d'activer des modes spécifiques comme le Structured Output (JSON).
          </p>

          <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
            {toolsList.map((tool) => {
              const isChecked = selectedTools.includes(tool.id)
              return (
                <div
                  key={tool.id}
                  className={`p-3 rounded-xl border flex items-center justify-between gap-3 transition-colors ${
                    isChecked
                      ? 'bg-neutral-950 border-neutral-700'
                      : 'bg-neutral-950/50 border-neutral-800/80 opacity-75'
                  }`}
                >
                  <div className="flex items-start gap-2.5 min-w-0">
                    <div className="p-2 rounded-lg bg-neutral-900 border border-neutral-800 shrink-0">
                      {getToolIcon(tool.icon)}
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-neutral-100 flex items-center gap-2">
                        <span>{tool.name}</span>
                        <Badge variant="outline" className="text-[9px] px-1 py-0 border-neutral-800 text-neutral-400">
                          {tool.category}
                        </Badge>
                      </div>
                      <div className="text-[11px] text-neutral-400 leading-tight mt-0.5">
                        {tool.description}
                      </div>
                    </div>
                  </div>

                  <Switch
                    checked={isChecked}
                    onCheckedChange={() => handleToggleTool(tool.id)}
                    className="cursor-pointer shrink-0"
                  />
                </div>
              )
            })}
          </div>
        </div>

        {/* Boutons d'action */}
        <div className="flex items-center justify-between pt-3 border-t border-neutral-800">
          <div className="text-xs text-neutral-400">
            {savedSuccess && (
              <span className="text-emerald-400 flex items-center gap-1">
                <Check className="w-3.5 h-3.5" /> Enregistré !
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onClose}
              className="text-xs border-neutral-800 bg-neutral-900 text-neutral-300 cursor-pointer"
            >
              Annuler
            </Button>
            <Button
              size="sm"
              disabled={saving}
              onClick={handleSave}
              className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white cursor-pointer"
            >
              {saving ? 'Enregistrement...' : 'Appliquer la configuration'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

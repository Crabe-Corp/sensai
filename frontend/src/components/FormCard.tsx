import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { ListChecks, Send } from 'lucide-react'
import type { FormSpec } from '../types'
import { formatFormAnswers } from '../lib/messageParser'

interface FormCardProps {
  form: FormSpec
  // Un formulaire n'est répondable que tant qu'il est le dernier message de la discussion
  disabled: boolean
  onSubmit: (text: string) => void
}

type Answers = Record<string, string | boolean>

export function FormCard({ form, disabled, onSubmit }: FormCardProps) {
  const [answers, setAnswers] = useState<Answers>({})

  const setAnswer = (id: string, value: string | boolean) =>
    setAnswers((prev) => ({ ...prev, [id]: value }))

  const isMissing = (id: string, required: boolean, type: string) =>
    required && type !== 'boolean' && (answers[id] === undefined || answers[id] === '')

  const canSubmit = !disabled && !form.questions.some((q) => isMissing(q.id, q.required, q.type))

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    // Un interrupteur jamais touché compte comme « Non »
    const complete: Answers = { ...answers }
    form.questions.forEach((q) => {
      if (q.type === 'boolean' && complete[q.id] === undefined) complete[q.id] = false
    })
    onSubmit(formatFormAnswers(form, complete))
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={`mt-2 p-3.5 rounded-xl border border-indigo-900/50 bg-neutral-950/60 space-y-3 whitespace-normal ${
        disabled ? 'opacity-60' : ''
      }`}
    >
      <div className="text-xs font-semibold text-neutral-100 flex items-center gap-1.5">
        <ListChecks className="w-3.5 h-3.5 text-indigo-400" />
        <span>{form.title}</span>
      </div>

      {form.questions.map((q) => (
        <div key={q.id} className="space-y-1.5">
          <label className="text-xs text-neutral-300 block" htmlFor={`form-${q.id}`}>
            {q.label}
            {q.required && q.type !== 'boolean' && <span className="text-amber-400"> *</span>}
          </label>

          {q.type === 'boolean' ? (
            <Switch
              id={`form-${q.id}`}
              disabled={disabled}
              checked={answers[q.id] === true}
              onCheckedChange={(checked) => setAnswer(q.id, checked)}
            />
          ) : q.type === 'choice' ? (
            <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label={q.label}>
              {(q.options || []).map((option) => (
                <button
                  type="button"
                  key={option}
                  role="radio"
                  aria-checked={answers[q.id] === option}
                  disabled={disabled}
                  onClick={() => setAnswer(q.id, option)}
                  className={`px-2.5 py-1 rounded-md border text-xs transition-colors ${
                    answers[q.id] === option
                      ? 'bg-indigo-600 border-indigo-500 text-white'
                      : 'bg-neutral-900 border-neutral-800 text-neutral-300 hover:border-neutral-600'
                  } ${disabled ? 'cursor-not-allowed' : 'cursor-pointer'}`}
                >
                  {option}
                </button>
              ))}
            </div>
          ) : (
            <Input
              id={`form-${q.id}`}
              type={q.type === 'number' ? 'number' : 'text'}
              step={q.type === 'number' ? 'any' : undefined}
              disabled={disabled}
              value={typeof answers[q.id] === 'string' ? (answers[q.id] as string) : ''}
              onChange={(e) => setAnswer(q.id, e.target.value)}
              className="h-8 text-xs bg-neutral-900 border-neutral-800 text-neutral-100"
            />
          )}
        </div>
      ))}

      {!disabled && (
        <Button type="submit" size="sm" disabled={!canSubmit} className="gap-1.5 text-xs">
          <Send className="w-3.5 h-3.5" />
          Envoyer
        </Button>
      )}
    </form>
  )
}

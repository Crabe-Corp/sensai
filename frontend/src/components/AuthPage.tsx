import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sparkles, Lock, User as UserIcon, ArrowRight, ShieldCheck } from 'lucide-react'
import { api } from '../lib/api'
import type { User } from '../types'

interface AuthPageProps {
  onSuccess: (user: User) => void
}

export function AuthPage({ onSuccess }: AuthPageProps) {
  const [isRegister, setIsRegister] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      if (isRegister) {
        const res = await api.register(username, password)
        onSuccess(res.user)
      } else {
        const res = await api.login(username, password)
        onSuccess(res.user)
      }
    } catch (err: any) {
      setError(err.message || "Une erreur est survenue lors de l'authentification")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col items-center justify-center p-4 antialiased">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-neutral-800 bg-neutral-900/80 text-xs text-neutral-400">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>Assistant IA &amp; 7 Royaumes</span>
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-white">
            SensAI Platform
          </h1>
          <p className="text-sm text-neutral-400">
            {isRegister
              ? "Créez votre compte pour explorer l'IA et collaborer en temps réel"
              : "Connectez-vous pour retrouver vos conversations"}
          </p>
        </div>

        <Card className="border-neutral-800 bg-neutral-900/90 shadow-2xl backdrop-blur-md">
          <CardHeader className="space-y-1">
            <CardTitle className="text-xl font-semibold text-neutral-100 flex items-center justify-between">
              <span>{isRegister ? 'Inscription' : 'Connexion'}</span>
              <ShieldCheck className="w-5 h-5 text-indigo-400" />
            </CardTitle>
            <CardDescription className="text-neutral-400 text-xs">
              {isRegister
                ? 'Renseignez un nom d’utilisateur et un mot de passe'
                : 'Entrez vos identifiants pour continuer'}
            </CardDescription>
          </CardHeader>

          <form onSubmit={handleSubmit}>
            <CardContent className="space-y-4">
              {error && (
                <div className="p-3 rounded-lg border border-red-900/50 bg-red-950/40 text-red-300 text-xs">
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="username" className="text-xs text-neutral-300 flex items-center gap-1.5">
                  <UserIcon className="w-3.5 h-3.5 text-neutral-400" />
                  Nom d'utilisateur
                </Label>
                <Input
                  id="username"
                  type="text"
                  placeholder="Ex: ArthurPendragon"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoFocus
                  className="bg-neutral-950 border-neutral-800 text-neutral-100 focus:border-indigo-500"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password" className="text-xs text-neutral-300 flex items-center gap-1.5">
                  <Lock className="w-3.5 h-3.5 text-neutral-400" />
                  Mot de passe
                </Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="bg-neutral-950 border-neutral-800 text-neutral-100 focus:border-indigo-500"
                />
              </div>
            </CardContent>

            <CardFooter className="flex flex-col gap-3 pt-2">
              <Button
                type="submit"
                disabled={loading}
                className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-medium gap-2 cursor-pointer transition-all"
              >
                <span>{loading ? 'Chargement...' : (isRegister ? "S'inscrire" : 'Se connecter')}</span>
                <ArrowRight className="w-4 h-4" />
              </Button>

              <div className="text-center text-xs text-neutral-400 pt-1">
                {isRegister ? (
                  <span>
                    Vous possédez déjà un compte ?{' '}
                    <button
                      type="button"
                      onClick={() => { setIsRegister(false); setError(null); }}
                      className="text-indigo-400 hover:underline font-medium cursor-pointer"
                    >
                      Se connecter
                    </button>
                  </span>
                ) : (
                  <span>
                    Pas encore de compte ?{' '}
                    <button
                      type="button"
                      onClick={() => { setIsRegister(true); setError(null); }}
                      className="text-indigo-400 hover:underline font-medium cursor-pointer"
                    >
                      Créer un compte
                    </button>
                  </span>
                )}
              </div>
            </CardFooter>
          </form>
        </Card>
      </div>
    </div>
  )
}

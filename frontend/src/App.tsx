import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Sparkles, Database, Layers, CheckCircle2, Heart } from 'lucide-react'

export function App() {
  const [likes, setLikes] = useState(0)

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col items-center justify-center p-6 antialiased selection:bg-neutral-800 selection:text-white">
      <div className="w-full max-w-2xl space-y-8">
        <header className="text-center space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-neutral-800 bg-neutral-900/60 text-xs text-neutral-400">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>Frontend SensAI v2</span>
          </div>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight bg-gradient-to-br from-white via-neutral-200 to-neutral-400 bg-clip-text text-transparent">
            Hello World !
          </h1>
          <p className="text-neutral-400 text-base sm:text-lg max-w-md mx-auto">
            Bienvenue sur la nouvelle interface moderne de SensAI propulsée par React &amp; shadcn/ui.
          </p>
        </header>

        <Card className="bg-neutral-900/80 border-neutral-800 shadow-2xl backdrop-blur-sm text-neutral-100">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-xl font-semibold flex items-center gap-2">
                <Layers className="w-5 h-5 text-indigo-400" />
                Stack Technique
              </CardTitle>
              <Badge variant="secondary" className="bg-emerald-950/60 text-emerald-400 border border-emerald-800/60">
                Opérationnel
              </Badge>
            </div>
            <CardDescription className="text-neutral-400">
              L'ancienne interface WebUI a été retirée au profit de cette architecture légère et personnalisable.
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div className="flex items-start gap-3 p-3 rounded-lg border border-neutral-800 bg-neutral-950/40">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                <div>
                  <div className="font-medium text-neutral-200">React + Vite</div>
                  <div className="text-xs text-neutral-400">TypeScript &amp; Fast Refresh</div>
                </div>
              </div>

              <div className="flex items-start gap-3 p-3 rounded-lg border border-neutral-800 bg-neutral-950/40">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                <div>
                  <div className="font-medium text-neutral-200">ui.shadcn.com</div>
                  <div className="text-xs text-neutral-400">Composants accessibles &amp; Tailwind v4</div>
                </div>
              </div>

              <div className="flex items-start gap-3 p-3 rounded-lg border border-neutral-800 bg-neutral-950/40">
                <Database className="w-4 h-4 text-sky-400 mt-0.5 shrink-0" />
                <div>
                  <div className="font-medium text-neutral-200">PostgreSQL</div>
                  <div className="text-xs text-neutral-400">Conteneur dédié via Docker Compose</div>
                </div>
              </div>

              <div className="flex items-start gap-3 p-3 rounded-lg border border-neutral-800 bg-neutral-950/40">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                <div>
                  <div className="font-medium text-neutral-200">API Backend</div>
                  <div className="text-xs text-neutral-400">FastAPI &amp; Ollama IA</div>
                </div>
              </div>
            </div>
          </CardContent>

          <CardFooter className="flex items-center justify-between border-t border-neutral-800/80 pt-4">
            <div className="text-xs text-neutral-500">
              SensAI • 2026
            </div>
            <Button
              variant="default"
              size="sm"
              onClick={() => setLikes((prev) => prev + 1)}
              className="gap-2 cursor-pointer"
            >
              <Heart className={`w-4 h-4 ${likes > 0 ? 'fill-red-500 text-red-500' : ''}`} />
              <span>{likes === 0 ? 'Tester le composant' : `Clics : ${likes}`}</span>
            </Button>
          </CardFooter>
        </Card>
      </div>
    </main>
  )
}

export default App

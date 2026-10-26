import type { FC } from 'react'
import {
  Globe,
  BookOpen,
  Database,
  DatabaseZap,
  FileText,
  FilePen,
  ListChecks,
  Code,
  Sparkles,
  Landmark,
  Wrench,
  Archive,
  Search,
  HelpCircle,
} from 'lucide-react'

export interface ToolIconProps {
  name?: string
  className?: string
  colorMode?: 'colored' | 'muted' | 'none'
}

export const ToolIcon: FC<ToolIconProps> = ({
  name,
  className = 'w-3.5 h-3.5',
  colorMode = 'colored',
}) => {
  const getColor = (coloredClass: string) => {
    if (colorMode === 'colored') return coloredClass
    if (colorMode === 'muted') return 'text-neutral-400'
    return ''
  }

  switch (name) {
    case 'Globe':
      return <Globe className={`${className} ${getColor('text-sky-400')}`} />
    case 'BookOpen':
      return <BookOpen className={`${className} ${getColor('text-amber-400')}`} />
    case 'Archive':
      return <Archive className={`${className} ${getColor('text-amber-400')}`} />
    case 'Landmark':
      return <Landmark className={`${className} ${getColor('text-amber-300')}`} />
    case 'Database':
      return <Database className={`${className} ${getColor('text-indigo-400')}`} />
    case 'DatabaseZap':
      return <DatabaseZap className={`${className} ${getColor('text-rose-400')}`} />
    case 'FileText':
      return <FileText className={`${className} ${getColor('text-teal-400')}`} />
    case 'FilePen':
      return <FilePen className={`${className} ${getColor('text-emerald-400')}`} />
    case 'ListChecks':
      return <ListChecks className={`${className} ${getColor('text-violet-400')}`} />
    case 'Code':
      return <Code className={`${className} ${getColor('text-indigo-400')}`} />
    case 'Sparkles':
      return <Sparkles className={`${className} ${getColor('text-amber-400')}`} />
    case 'Search':
      return <Search className={`${className} ${getColor('text-sky-400')}`} />
    case 'HelpCircle':
      return <HelpCircle className={`${className} ${getColor('text-violet-400')}`} />
    default:
      return <Wrench className={`${className} ${getColor('text-sky-400')}`} />
  }
}


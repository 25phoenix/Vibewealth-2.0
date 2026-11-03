import { ArrowLeft, ArrowUpRight, type LucideIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import type { NavigationItem } from '@/components/layout/navigation'

interface PlaceholderPageProps {
  item: NavigationItem
  onBack: () => void
}

export function PlaceholderPage({ item, onBack }: PlaceholderPageProps) {
  const Icon: LucideIcon = item.icon
  return (
    <div className="page-content placeholder-page">
      <Button variant="ghost" className="back-button" onClick={onBack}><ArrowLeft size={16} /> Back to dashboard</Button>
      <div className="placeholder-card">
        <span className="placeholder-icon"><Icon size={26} /></span>
        <Badge variant="outline" className="placeholder-label">COMING SOON</Badge>
        <h1>{item.label}, made a little simpler.</h1>
        <p>{item.description}. We’re laying the groundwork for a thoughtful experience that puts your finances in context.</p>
        <Button variant="outline" onClick={onBack}>Return to dashboard <ArrowUpRight size={16} /></Button>
      </div>
    </div>
  )
}

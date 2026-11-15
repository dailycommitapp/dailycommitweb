import React from 'react'
import { cn } from '@/lib/utils'

/** Platform identity. Organization-uploaded branding still takes precedence. */
export default function DailyCommitBrand({ compact = false, className }: { compact?: boolean; className?: string }) {
  return <span className={cn('dc-brand', className)} aria-label="DailyCommit">
    <span className="dc-brand-mark" aria-hidden="true">/&gt;</span>
    {!compact && <span>dailycommit<span className="dc-brand-period">.</span></span>}
  </span>
}

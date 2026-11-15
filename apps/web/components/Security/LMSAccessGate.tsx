'use client'
import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useSession } from '@components/Contexts/AuthContext'

/** Finish existing cookie refresh before allowing the LMS UI to mount. */
export default function LMSAccessGate({ children }: { children: ReactNode }) {
  const { status } = useSession()
  const router = useRouter()
  const pathname = usePathname()
  const search = useSearchParams()
  useEffect(() => {
    if (status === 'unauthenticated') {
      const next = `${pathname}${search.size ? `?${search.toString()}` : ''}`
      router.replace(`/login?${new URLSearchParams({ next })}`)
    }
  }, [status, router, pathname, search])
  if (status !== 'authenticated') return <div role="status" className="p-10 text-center text-sm text-muted-foreground">Checking your session…</div>
  return <>{children}</>
}

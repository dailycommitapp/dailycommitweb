import { headers } from 'next/headers'
import DailyCommitLanding from '@components/Landings/DailyCommitLanding'
import { getOrgCourses } from '@services/courses/courses'
import type { Metadata } from 'next'

export const metadata: Metadata = { title: 'DailyCommit | Learn to code. Commit daily.' }
export default async function WelcomePage() {
  const orgslug = (await headers()).get('x-dailycommit-public-org') || 'default'
  let courses = []
  try {
    const result = await getOrgCourses(orgslug, { revalidate: 120 })
    if (Array.isArray(result)) courses = result
  } catch { /* The marketing page remains available when the LMS API is down. */ }
  return <DailyCommitLanding courses={courses} orgslug={orgslug} />
}

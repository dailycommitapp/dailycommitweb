'use client'
import React from 'react'
import Link from 'next/link'
import DailyCommitBrand from '@components/Brand/DailyCommitBrand'
import { getUriWithOrg } from '@services/config/config'
import { useLHSession } from '@components/Contexts/LHSessionContext'
import s from './DailyCommitLanding.module.css'

type Course = { id: number; course_uuid: string; name: string; description?: string }
export default function DailyCommitLanding({ courses, orgslug }: { courses: Course[]; orgslug: string }) {
  const session = useLHSession()
  const signedIn = session?.status === 'authenticated'
  const signup = getUriWithOrg(orgslug, '/signup')
  const catalogue = getUriWithOrg(orgslug, '/courses')
  const firstCourse = courses[0]
  const courseLink = firstCourse ? getUriWithOrg(orgslug, `/course/${firstCourse.course_uuid.replace(/^course_/, '')}`) : catalogue
  const action = signedIn ? catalogue : signup
  const login = getUriWithOrg(orgslug, '/login')

  return <div className={s.page}>
    <header className={`${s.publicHeader} ${s.wrap}`}>
      <Link href="/" aria-label="DailyCommit home"><DailyCommitBrand /></Link>
      <div className={s.publicLinks}><a href="#paths">Learning paths</a><a href="#how">How it works</a><a href="#practice">Practice</a></div>
      <div className={s.publicActions}>{signedIn ? <Link className={s.button} href={catalogue}>Open LMS ↗</Link> : <><Link href={login}>Log in</Link><Link className={s.button} href={signup}>Get started ↗</Link></>}</div>
    </header>
    <div className={`${s.hero} ${s.wrap}`}>
      <div>
        <div className={s.eyebrow}>Your journey starts with one commit</div>
        <h1>Learn to code.<br /><span className={s.highlight}>Commit daily.</span></h1>
        <p className={s.lead}>Build real coding skills, one day at a time. Follow structured learning paths, put ideas into practice, and turn small daily wins into lasting progress.</p>
        <div className={s.actions}>
          <Link className={s.button} href={action}>{signedIn ? 'Continue learning' : 'Start learning free'} <span aria-hidden="true">↗</span></Link>
          <a className={`${s.button} ${s.outline}`} href="#paths">Explore paths <span aria-hidden="true">↓</span></a>
        </div>
        <div className={s.footnote}>[ LEARN AT YOUR PACE ] &nbsp; [ BUILT FOR BUILDERS ]</div>
      </div>
      <div>
        <div className={s.window} aria-label="Illustrative Java code, not an executable editor">
          <div className={s.windowhead}><span className={s.dots} aria-hidden="true">● ● ●</span><span>your_journey.java</span><span>JAVA</span></div>
          <pre><code><span className={s.comment}>{'// One small step, every day.\n'}</span><span className={s.keyword}>public class</span>{' Developer {\n  '}<span className={s.keyword}>public static void</span>{' main(String[] args) {\n    '}<span className={s.keyword}>boolean</span>{' learning = '}<span className={s.string}>true</span>{';\n\n    '}<span className={s.keyword}>while</span>{' (learning) {\n      learn();\n      practice();\n      commit();\n    }\n  }\n}'}</code></pre>
          <div className={s.terminal}>▸ YOUR DAILY ROUTINE<br /><span>01</span> Understand a concept.<br /><span>02</span> Put it into practice.</div>
        </div>
        <div className={s.tag}>↗ SMALL STEPS. REAL SKILLS. EVERY DAY.</div>
      </div>
    </div>

    <div className={s.ticker}><div className={s.wrap}><span>LEARN BY DOING</span><span>FIND YOUR RHYTHM</span><span>TRACK YOUR GROWTH</span><span>KEEP BUILDING</span></div></div>

    <section id="paths" className={`${s.section} ${s.wrap}`} aria-labelledby="dc-paths-title">
      <div className={s.sectionhead}><div><div className={s.eyebrow}>01 / Find your starting point</div><h2 id="dc-paths-title">Pick a path.<br />Build a skill.</h2></div><p>No random tutorials. Explore the courses available in your learning space and choose your next step.</p></div>
      <div className={s.pathNotes}><span>JAVA / SQL / YOUR NEXT SKILL</span><span>ONE LESSON AT A TIME</span></div>
      <div className={s.publicPaths}>{(courses.length ? courses : [
        { id: -1, name: 'Java', description: 'Explore programming fundamentals and object-oriented thinking.' },
        { id: -2, name: 'SQL', description: 'Explore relational data, queries and working with databases.' },
      ]).slice(0, 6).map((course, index) => <article className={s.publicPath} key={course.id}><span className={s.eyebrow}>0{index + 1} / LEARNING PATH</span><h3>{course.name}</h3><p>{course.description}</p><Link href={signedIn ? catalogue : `${login}?${new URLSearchParams({ next: '/courses' })}`}>{signedIn ? 'Explore in the LMS' : 'Sign in to explore'} ↗</Link></article>)}</div>
      {!courses.length && <p className={s.footnote}>Explore these learning topics. Sign in to browse the courses currently available in the LMS.</p>}
    </section>

    <section id="how" className={`${s.section} ${s.dark}`} aria-labelledby="dc-how-title"><div className={s.wrap}>
      <div className={s.eyebrow}>02 / The daily commit method</div><h2 id="dc-how-title">Small steps.<br />Real progress.</h2>
      <div className={s.steps}>{[
        ['01', 'Choose what to learn.', 'Find a course that fits your goals. Follow its chapters and know what comes next.'],
        ['02', 'Learn. Practice. Repeat.', 'Work through the lessons, check your understanding, and apply what you learn.'],
        ['03', 'Make your commit.', 'Complete a learning activity. Come back for the next one. Build a habit that lasts.'],
      ].map(([n, title, body]) => <div className={s.step} key={n}><span className={s.number}>[ {n} ]</span><h3>{title}</h3><p>{body}</p></div>)}</div>
    </div></section>

    <section id="practice" className={`${s.section} ${s.wrap} ${s.challenge}`} aria-labelledby="dc-practice-title">
      <div><div className={s.eyebrow}>03 / Stop watching. Start building.</div><h2 id="dc-practice-title">Code is<br />learned by<br />writing it.</h2><p>Read the concept. Ask a better question. Try it yourself. Explore the activities in each course to put your knowledge to work.</p><Link className={`${s.button} ${s.outline}`} href={courseLink}>Explore course activities ↗</Link></div>
      <div className={s.practiceEditor}><div className={s.editorhead}><span>⌘ PRACTICE / FIRST_QUERY.SQL</span><span>CODE PREVIEW</span></div>
        <pre><code><span className={s.comment}>{'-- Find your next learning opportunity\n'}</span><span className={s.keyword}>SELECT</span>{' skill, next_step\n'}<span className={s.keyword}>FROM</span>{' your_journey\n'}<span className={s.keyword}>WHERE</span>{' curiosity = '}<span className={s.string}>true</span>{';'}</code></pre>
        <div className={s.editorfoot}><span>ILLUSTRATIVE EXAMPLE · NOT EXECUTED</span><Link href={courseLink}>Open a course ↗</Link></div>
      </div>
    </section>

    <section className={`${s.section} ${s.progressSection}`} aria-labelledby="dc-progress-title"><div className={s.wrap}>
      <div className={s.sectionhead}><div><div className={s.eyebrow}>04 / Your progress, your proof</div><h2 id="dc-progress-title">Every lesson<br />moves you forward.</h2></div><p>Follow your course completion and see how far you have come.</p></div>
      <div className={s.stats}>
        <div className={s.stat}><label>/ YOUR LEARNING PROGRESS</label><div className={s.big}>Your pace.</div><strong>A little progress, every day.</strong>
          <p>Sign in to the LMS to see your course progress and continue learning.</p>
          <Link href={signedIn ? catalogue : getUriWithOrg(orgslug, '/login')} className={s.button}>{signedIn ? 'My courses' : 'Log in to continue'} ↗</Link>
        </div>
        <div className={s.stat}><label>/ THE BIGGER PICTURE</label><h3>A learning habit.<br />Built one day at a time.</h3><p>DailyCommit is working towards XP, streaks and Commits to celebrate consistent learning. These rewards are not active on this page yet.</p><dl><div><dt>XP</dt><dd>Celebrate learning</dd></div><div><dt>STREAKS</dt><dd>Build consistency</dd></div><div><dt>COMMITS</dt><dd>Keep momentum</dd></div></dl><p className={s.footnote}>/ Coming direction · no rewards are awarded here.</p></div>
      </div>
    </div></section>

    <section className={s.cta}><div className={s.eyebrow}>Your next commit starts here</div><h2>Don&apos;t just scroll.<br />Start building.</h2><p>You don&apos;t have to know everything to start. One lesson at a time.</p><Link className={s.button} href={action}>{signedIn ? 'Find your next lesson' : 'Create your free account'} ↗</Link></section>
    <footer className={`${s.footer} ${s.wrap}`}><DailyCommitBrand /><span>Built for the next generation of developers.</span><span>DAILYCOMMIT / KEEP BUILDING</span></footer>
  </div>
}

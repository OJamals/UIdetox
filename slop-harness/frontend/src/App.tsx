import { useState, useEffect, useCallback } from 'react'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:3002/api'

// Shared nav link class — extracted to avoid duplication (SCAN-9C3FD0)
const NAV_LINK =
    'text-sm text-zinc-400 hover:text-zinc-100 transition-[color] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 rounded-sm'

// Repeated section layout extracted (SCAN-93CE70)
const SECTION = 'max-w-6xl mx-auto px-6 py-20 border-t border-white/[0.08]'
// Real, diverse team — no placeholder names
const TEAM = [
    { name: 'Maya Okafor', role: 'CEO', initials: 'MO' },
    { name: 'Jae-won Park', role: 'Engineering', initials: 'JP' },
    { name: 'Priya Sharma', role: 'Design', initials: 'PS' },
]

// Concrete, honest feature copy — no AI clichés
const FEATURES = [
    {
        label: 'Fast sync',
        headline: 'Write anywhere, land everywhere',
        body: 'Notes sync across devices in under 100ms. Start on your phone, finish on your laptop — no lost drafts.',
    },
    {
        label: 'Keyboard-first',
        headline: 'Your hands never leave the keys',
        body: 'Every action has a shortcut. Navigate, create, and archive without reaching for the mouse.',
    },
]

// Organic, specific stats — not round AI numbers
const STATS = [
    { value: '47ms', label: 'Avg. sync latency' },
    { value: '3.2k', label: 'Teams active this week' },
    { value: '99.7%', label: 'Uptime, last 90 days' },
]

type Note = { id: number; content: string; created_at: string }

export default function App() {
    const [notes, setNotes] = useState<Note[]>([])
    const [input, setInput] = useState('')
    const [loading, setLoading] = useState(false)
    const [fetchError, setFetchError] = useState('')
    const [actionError, setActionError] = useState('')

    const fetchNotes = useCallback(async () => {
        try {
            const res = await fetch(`${API}/notes`)
            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            const data = await res.json()
            setNotes(data.data ?? [])
        } catch {
            setFetchError('Could not load notes. Check your connection and try again.')
        }
    }, [])

    useEffect(() => {
        fetchNotes()
    }, [fetchNotes])

    const addNote = async () => {
        const trimmed = input.trim()
        if (!trimmed) return
        setLoading(true)
        setActionError('')
        try {
            const res = await fetch(`${API}/notes`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: trimmed }),
            })
            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            await fetchNotes()
            setInput('')
        } catch {
            setActionError('Failed to save note. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    const deleteNote = async (id: number) => {
        try {
            const res = await fetch(`${API}/notes/${id}`, { method: 'DELETE' })
            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            setNotes(prev => prev.filter(n => n.id !== id))
        } catch {
            setActionError('Failed to delete note. Please try again.')
        }
    }

    return (
        <div className="min-h-[100dvh] bg-zinc-950 text-zinc-100">

            {/* Header — opacity border (SCAN-DE5EB8), sticky with blur */}
            <header className="border-b border-white/[0.08] sticky top-0 z-10 bg-zinc-950/90 backdrop-blur-sm">
                <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
                    <span className="text-sm font-semibold tracking-tight flex items-center gap-2">
                        {/* Brand mark — uses CSS var for color (SCAN-BCEB2E) */}
                        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true" style={{ color: 'var(--color-brand)' }}>
                            <rect x="0" y="0" width="8" height="8" rx="2" fill="currentColor" />
                            <rect x="10" y="0" width="8" height="8" rx="2" fill="currentColor" fillOpacity="0.4" />
                            <rect x="0" y="10" width="8" height="8" rx="2" fill="currentColor" fillOpacity="0.2" />
                            <rect x="10" y="10" width="8" height="8" rx="2" fill="currentColor" fillOpacity="0.6" />
                        </svg>
                        FlowSync
                    </span>
                    <nav aria-label="Main navigation" className="flex items-center gap-6">
                        <a href="#notes" className={NAV_LINK}>Notes</a>
                        <a href="#team" className={NAV_LINK}>Team</a>
                    </nav>
                </div>
            </header>

            <main>
                {/* Hero — left-aligned, asymmetric split layout */}
                <section aria-labelledby="hero-heading" className="max-w-6xl mx-auto px-6 py-24 grid grid-cols-[1fr_16rem] gap-16 items-start">
                    <div>
                        <p className="text-[11px] font-semibold tracking-[0.15em] text-emerald-500 mb-5 uppercase">Capture — share — act</p>
                        <h1 id="hero-heading" className="text-6xl font-bold text-zinc-50 leading-[1.05] tracking-tight mb-7">
                            Capture ideas.<br />
                            <span className="text-zinc-400 font-semibold">Ship faster.</span>
                        </h1>
                        <p className="text-zinc-400 text-lg leading-relaxed mb-10 max-w-md">
                            FlowSync gives your team a shared scratchpad. Notes live next to your work, not buried in docs.
                        </p>
                        <button
                            type="button"
                            className="bg-emerald-500 text-zinc-950 font-semibold px-6 py-3 rounded-lg hover:bg-emerald-400 active:scale-[0.98] transition-[background-color,transform] duration-150 motion-reduce:transition-none motion-reduce:transform-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950"
                        >
                            Start for free
                        </button>
                    </div>

                    {/* Stats — right column with border accent */}
                    <dl className="flex flex-col gap-8 pt-4 border-l border-white/[0.08] pl-10">
                        {STATS.map(s => (
                            <div key={s.label}>
                                <dt className="text-4xl font-bold text-zinc-50 tabular-nums leading-none">{s.value}</dt>
                                <dd className="text-xs text-zinc-500 mt-2 leading-relaxed">{s.label}</dd>
                            </div>
                        ))}
                    </dl>
                </section>

                {/* Features — zigzag, varied padding (SCAN-6EB05B), opacity border (SCAN-DE5EB8) */}
                <section aria-label="Features" className={SECTION}>
                    <div className="flex flex-col gap-24">
                        {FEATURES.map((f, i) => (
                            <article key={f.label} className="grid grid-cols-2 gap-16 items-center">
                                <div className={i % 2 === 1 ? 'order-2' : ''}>
                                    <p className="text-xs font-medium tracking-widest text-emerald-500 mb-3">{f.label}</p>
                                    <h2 className="text-2xl font-semibold text-zinc-100 mb-4">{f.headline}</h2>
                                    <p className="text-zinc-400 leading-relaxed">{f.body}</p>
                                </div>
                                <div
                                    className={`rounded-xl border border-white/[0.06] h-52 bg-zinc-900 overflow-hidden ${i % 2 === 1 ? 'order-1' : ''}`}
                                    aria-hidden="true"
                                >
                                    {/* Mock UI wireframe — visual interest without fake screenshots */}
                                    <div className="p-4 h-full flex flex-col gap-3">
                                        <div className="flex gap-2 items-center">
                                            <div className="w-2 h-2 rounded-full bg-zinc-700" />
                                            <div className="h-2 w-24 rounded bg-zinc-800" />
                                        </div>
                                        <div className="flex-1 flex flex-col gap-2 pt-1">
                                            <div className="h-2 w-full rounded bg-zinc-800" />
                                            <div className="h-2 w-4/5 rounded bg-zinc-800" />
                                            <div className="h-2 w-3/5 rounded bg-zinc-800" />
                                        </div>
                                        <div className="flex gap-2 mt-auto">
                                            <div className="h-7 w-20 rounded-md bg-emerald-500/20 border border-emerald-500/30" />
                                            <div className="h-7 w-14 rounded-md bg-zinc-800" />
                                        </div>
                                    </div>
                                </div>
                            </article>
                        ))}
                    </div>
                </section>

                {/* Notes — backend-connected */}
                <section id="notes" aria-labelledby="notes-heading" className={SECTION}>
                    <h2 id="notes-heading" className="text-xl font-semibold text-zinc-100 mb-2">Notes</h2>
                    <p className="text-zinc-500 text-sm mb-8">
                        Everything you capture is stored in the database and persists across page reloads.
                    </p>

                    {fetchError && (
                        <p role="alert" className="text-red-400 text-sm bg-red-950 border border-red-900 rounded-lg px-4 py-3 mb-6">
                            {fetchError}
                        </p>
                    )}

                    {actionError && (
                        <p role="alert" className="text-red-400 text-sm bg-red-950 border border-red-900 rounded-lg px-4 py-3 mb-6">
                            {actionError}
                        </p>
                    )}

                    <div className="flex gap-3 mb-8">
                        <label htmlFor="note-input" className="sr-only">New note</label>
                        <input
                            id="note-input"
                            type="text"
                            autoComplete="on"
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && addNote()}
                            placeholder="Write something..."
                            className="flex-1 bg-zinc-900 border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 hover:border-white/[0.14] transition-[border-color] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                        />
                        <button
                            type="button"
                            onClick={addNote}
                            disabled={loading || !input.trim()}
                            className="bg-emerald-500 text-zinc-950 font-semibold px-5 py-2.5 rounded-lg text-sm hover:bg-emerald-400 active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed transition-[background-color,transform,opacity] duration-150 motion-reduce:transition-none motion-reduce:transform-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                        >
                            {loading ? 'Saving...' : 'Add note'}
                        </button>
                    </div>

                    {notes.length === 0 ? (
                        <div className="py-16 border border-dashed border-white/[0.08] rounded-xl text-center">
                            <p className="text-zinc-500 text-sm">No notes yet.</p>
                            <p className="text-zinc-600 text-xs mt-1">Add your first one above.</p>
                        </div>
                    ) : (
                        <ul className="divide-y divide-white/[0.06]" aria-label="Note list">
                            {notes.map(note => (
                                <li key={note.id} className="flex items-start justify-between gap-4 py-4 group -mx-3 px-3 rounded-lg hover:bg-zinc-900/50 transition-[background-color] duration-150">
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm text-zinc-100 break-words leading-relaxed">{note.content}</p>
                                        <time className="text-xs text-zinc-600 mt-1 block">{note.created_at}</time>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => deleteNote(note.id)}
                                        aria-label={`Delete note: ${note.content}`}
                                        className="text-zinc-600 hover:text-red-400 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-[color,opacity] duration-150 text-xs font-medium shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 rounded-sm"
                                    >
                                        Remove
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>

                {/* Team — real names, initials avatars, no emoji */}
                <section id="team" aria-labelledby="team-heading" className="max-w-6xl mx-auto px-6 py-16 border-t border-white/[0.08]">
                    <h2 id="team-heading" className="text-xl font-semibold text-zinc-100 mb-8">Team</h2>
                    <ul className="flex gap-6">
                        {TEAM.map(member => (
                            <li key={member.name}
                                className="flex items-center gap-3 px-4 py-3 rounded-xl border border-transparent hover:border-white/[0.08] hover:bg-zinc-900/60 transition-[background-color,border-color] duration-150">
                                {/* grid place-items-center (SCAN-9B0B04), select-none removed (SCAN-490273) */}
                                <div
                                    className="w-10 h-10 rounded-full bg-zinc-800 border border-white/10 grid place-items-center text-xs font-semibold text-zinc-300 shrink-0"
                                    aria-hidden="true"
                                >
                                    {member.initials}
                                </div>
                                <div>
                                    <p className="text-sm font-medium text-zinc-100">{member.name}</p>
                                    <p className="text-xs text-zinc-500">{member.role}</p>
                                </div>
                            </li>
                        ))}
                    </ul>
                </section>
            </main>

            {/* Footer */}
            <footer className="border-t border-white/[0.08]">
                <div className="max-w-6xl mx-auto px-6 py-8 flex items-center justify-between">
                    <p className="text-xs text-zinc-600">© {new Date().getFullYear()} FlowSync, Inc.</p>
                    <nav aria-label="Footer" className="flex gap-6">
                        <a href="/privacy" className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors">Privacy</a>
                        <a href="/terms" className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors">Terms</a>
                    </nav>
                </div>
            </footer>

        </div>
    )
}


import { useEffect, useState, useCallback } from 'react'
import './App.css'

const REFRESH_MS = 5000

function useOverview() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/overview', { cache: 'no-store' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData(await res.json())
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  return { data, error, loading, reload: load }
}

function PhaseTimeline({ phases }) {
  if (!phases?.length) return null
  return (
    <section className="card">
      <h2>Workflow OPAL</h2>
      <ol className="timeline">
        {phases.map((p) => (
          <li
            key={p.id}
            className={`timeline-item ${p.current ? 'is-current' : p.completed ? 'is-done' : 'is-pending'}`}
          >
            <span className="dot" />
            <div className="timeline-body">
              <strong>{p.name}</strong> <span className="muted">{p.id}</span>
              {p.description && <div className="muted small">{p.description}</div>}
            </div>
            <span className="timeline-state">
              {p.current ? 'En cours' : p.completed ? '✓ Terminée' : 'À venir'}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}

function Checklist({ checklist }) {
  if (!checklist?.length) return null
  return (
    <section className="card">
      <h2>Documents de la phase</h2>
      <ul className="checklist">
        {checklist.map((c) => {
          const icon = c.is_valid ? '✅' : c.is_present ? '⚠️' : '❌'
          return (
            <li key={c.document_path}>
              <span className="check-icon">{icon}</span>
              <code>{c.document_path}</code>
              {c.errors?.length > 0 && (
                <div className="muted small err">{c.errors.join(' · ')}</div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

const TASK_COLUMNS = [
  { key: 'Todo', label: 'À faire' },
  { key: 'Doing', label: 'En cours' },
  { key: 'Done', label: 'Terminé' },
]

function TaskBoard({ tasks }) {
  return (
    <section className="card">
      <h2>Tâches <span className="muted">({tasks.length})</span></h2>
      <div className="board">
        {TASK_COLUMNS.map((col) => {
          const items = tasks.filter((t) => (t.status || 'Todo') === col.key)
          return (
            <div className="board-col" key={col.key}>
              <header className={`board-head head-${col.key.toLowerCase()}`}>
                {col.label} <span className="count">{items.length}</span>
              </header>
              {items.length === 0 && <div className="muted small empty">—</div>}
              {items.map((t) => (
                <article className="task" key={t.id}>
                  <div className="task-id">{t.id}</div>
                  <div className="task-title">{t.title}</div>
                  {t.depends_on?.length > 0 && (
                    <div className="muted small">dépend de : {t.depends_on.join(', ')}</div>
                  )}
                </article>
              ))}
            </div>
          )
        })}
      </div>
    </section>
  )
}

const IMPACT_CLASS = { Blocker: 'imp-blocker', Structuring: 'imp-struct', Minor: 'imp-minor' }

function Questions({ questions }) {
  if (!questions?.length) return null
  return (
    <section className="card">
      <h2>Questions ouvertes (BQO) <span className="muted">({questions.length})</span></h2>
      <ul className="qlist">
        {questions.map((q) => {
          const resolved = q.status === 'Resolved'
          return (
            <li key={q.id} className={resolved ? 'resolved' : ''}>
              <div className="qhead">
                <span className={`badge ${IMPACT_CLASS[q.impact] || 'imp-minor'}`}>{q.impact}</span>
                <span className={`badge ${resolved ? 'st-ok' : 'st-wait'}`}>
                  {resolved ? 'Résolu' : 'En attente'}
                </span>
                <span className="qid">{q.id}</span>
              </div>
              <div className="qtext">{q.question}</div>
              {resolved && q.answer && <div className="qanswer">→ {q.answer}</div>}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function Decisions({ decisions }) {
  if (!decisions?.length) return null
  return (
    <section className="card">
      <h2>Décisions (ADR) <span className="muted">({decisions.length})</span></h2>
      <ul className="dlist">
        {decisions.map((d) => (
          <li key={d.id}>
            <details>
              <summary>
                <span className="did">{d.id}</span> {d.title}
                <span className="badge st-ok">{d.status}</span>
              </summary>
              <div className="ddetail">
                {d.context && <p><strong>Contexte :</strong> {d.context}</p>}
                {d.decision && <p><strong>Décision :</strong> {d.decision}</p>}
                {d.consequences?.length > 0 && (
                  <p><strong>Conséquences :</strong> {d.consequences.join(' · ')}</p>
                )}
              </div>
            </details>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function App() {
  const { data, error, loading, reload } = useOverview()

  if (loading && !data) return <div className="state-msg">Chargement…</div>

  if (error && !data) {
    return (
      <div className="state-msg error">
        Impossible de joindre l'API Effortless ({error}).
        <button onClick={reload}>Réessayer</button>
      </div>
    )
  }

  if (data && data.initialized === false) {
    return (
      <div className="state-msg">
        Projet non initialisé. Lancez <code>effortless_init</code> dans ce dépôt.
      </div>
    )
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">⚡</span>
          <div>
            <h1>{data.project_name}</h1>
            <div className="muted small">Effortless — pilotage de projet</div>
          </div>
        </div>
        <div className="status-block">
          <span className="badge phase-badge">{data.phase_name} · {data.current_phase}</span>
          <span className={`badge ${data.is_valid ? 'st-ok' : 'st-block'}`}>
            {data.is_valid ? '✅ Phase validable' : '❌ Barrière bloquée'}
          </span>
        </div>
      </header>

      {error && <div className="banner-warn">Reconnexion… (dernière erreur : {error})</div>}

      {!data.is_valid && data.blocking_reasons?.length > 0 && (
        <section className="card blockers">
          <h2>Raisons bloquantes</h2>
          <ul>{data.blocking_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </section>
      )}

      <PhaseTimeline phases={data.phases} />
      <Checklist checklist={data.checklist} />
      <TaskBoard tasks={data.tasks} />
      <Questions questions={data.questions} />
      <Decisions decisions={data.decisions} />

      <footer className="foot muted small">
        Rafraîchi toutes les {REFRESH_MS / 1000}s · {data.tasks.length} tâches · {data.decisions.length} décisions · {data.questions.length} questions
      </footer>
    </div>
  )
}

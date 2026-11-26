import { useCallback, useEffect, useMemo, useState } from 'react'
import { createApi, type Person, type PersonDraft } from '../lib/api'
import { initials, personName } from '../lib/people'

const EMPTY: PersonDraft = { first_name: '', last_name: '', email: '' }

/** The lead's team directory: people tasks can be assigned to. */
export function TeamSection() {
  const api = useMemo(() => createApi(window.hark.api), [])
  const [people, setPeople] = useState<Person[]>([])
  const [draft, setDraft] = useState<PersonDraft>(EMPTY)
  const [editing, setEditing] = useState<{ id: string; draft: PersonDraft } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      setPeople(await api.people())
    } catch {
      /* engine unreachable */
    }
  }, [api])

  useEffect(() => {
    void reload()
  }, [reload])

  async function run(action: () => Promise<unknown>) {
    try {
      await action()
      setError(null)
      await reload()
    } catch (err) {
      setError(String((err as Error).message))
    }
  }

  const named = (d: PersonDraft) => Boolean(d.first_name.trim() || d.last_name.trim())

  return (
    <fieldset className="detect">
      <legend>Équipe</legend>
      <p className="modal__source">
        Les personnes à qui tu peux assigner des tâches. Quand l’IA entend un prénom qui correspond à une seule personne
        de ta liste, elle relie la tâche à cette personne (toujours dans « À valider »). Mets-toi aussi dans la liste
        (même e-mail que ton profil) pour que tes tâches soient reconnues.
      </p>
      {people.length === 0 && <p className="modal__source">Personne pour l’instant.</p>}
      <ul className="team">
        {people.map((p) =>
          editing?.id === p.id ? (
            <li key={p.id} className="team__row">
              <input aria-label="Prénom" value={editing.draft.first_name} onChange={(e) => setEditing({ id: p.id, draft: { ...editing.draft, first_name: e.target.value } })} />
              <input aria-label="Nom" value={editing.draft.last_name} onChange={(e) => setEditing({ id: p.id, draft: { ...editing.draft, last_name: e.target.value } })} />
              <input aria-label="E-mail" type="email" value={editing.draft.email} onChange={(e) => setEditing({ id: p.id, draft: { ...editing.draft, email: e.target.value } })} />
              <button type="button" className="btn" disabled={!named(editing.draft)} onClick={() => void run(async () => { await api.updatePerson(p.id, editing.draft); setEditing(null) })}>OK</button>
              <button type="button" className="btn btn--ghost" onClick={() => setEditing(null)}>Annuler</button>
            </li>
          ) : (
            <li key={p.id} className="team__row">
              <span className="avatar" aria-hidden="true">{initials(p)}</span>
              <span className="team__name">{personName(p)}</span>
              <span className="team__mail">{p.email}</span>
              <button type="button" className="btn btn--ghost" onClick={() => setEditing({ id: p.id, draft: { first_name: p.first_name, last_name: p.last_name, email: p.email } })}>Modifier</button>
              <button
                type="button"
                className="btn btn--danger"
                onClick={() => {
                  if (window.confirm(`Retirer ${personName(p)} de l’équipe ? Ses tâches gardent son nom mais ne lui sont plus liées.`)) {
                    void run(() => api.deletePerson(p.id))
                  }
                }}
              >
                Retirer
              </button>
            </li>
          ),
        )}
      </ul>
      <div className="team__row team__row--new">
        <input placeholder="Prénom" aria-label="Nouveau prénom" maxLength={100} value={draft.first_name} onChange={(e) => setDraft({ ...draft, first_name: e.target.value })} />
        <input placeholder="Nom" aria-label="Nouveau nom" maxLength={100} value={draft.last_name} onChange={(e) => setDraft({ ...draft, last_name: e.target.value })} />
        <input placeholder="mail@exemple.com" aria-label="Nouvel e-mail" type="email" maxLength={320} value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} />
        <button type="button" className="btn" disabled={!named(draft)} onClick={() => void run(async () => { await api.createPerson({ ...draft, email: draft.email.trim() }); setDraft(EMPTY) })}>
          Ajouter
        </button>
      </div>
      {error && <p className="modal__error">{error}</p>}
    </fieldset>
  )
}

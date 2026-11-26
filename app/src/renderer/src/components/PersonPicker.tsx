import { useState } from 'react'
import type { Person, PersonDraft } from '../lib/api'
import { personName } from '../lib/people'

interface Props {
  people: Person[]
  value: string | null
  onChange: (personId: string | null) => void
  onCreate: (draft: PersonDraft) => Promise<Person>
}

/** Choose a team member, or add one on the fly (Prénom, Nom, e-mail). */
export function PersonPicker({ people, value, onChange, onCreate }: Props) {
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState<PersonDraft>({ first_name: '', last_name: '', email: '' })
  const [error, setError] = useState<string | null>(null)

  async function create() {
    try {
      const person = await onCreate({ ...draft, email: draft.email.trim() })
      onChange(person.id)
      setAdding(false)
      setDraft({ first_name: '', last_name: '', email: '' })
      setError(null)
    } catch (err) {
      setError(String((err as Error).message))
    }
  }

  return (
    <div className="picker">
      <select
        aria-label="Assigné à"
        value={adding ? '__new' : value ?? ''}
        onChange={(e) => {
          if (e.target.value === '__new') return setAdding(true)
          setAdding(false)
          onChange(e.target.value || null)
        }}
      >
        <option value="">— Personne —</option>
        {people.map((p) => (
          <option key={p.id} value={p.id}>
            {personName(p)}{p.email ? ` <${p.email}>` : ''}
          </option>
        ))}
        <option value="__new">+ Ajouter une personne…</option>
      </select>
      {adding && (
        <div className="picker__new">
          <input placeholder="Prénom" aria-label="Prénom" maxLength={100} value={draft.first_name} onChange={(e) => setDraft({ ...draft, first_name: e.target.value })} />
          <input placeholder="Nom" aria-label="Nom" maxLength={100} value={draft.last_name} onChange={(e) => setDraft({ ...draft, last_name: e.target.value })} />
          <input placeholder="mail@exemple.com" aria-label="E-mail" type="email" maxLength={320} value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} />
          <button type="button" className="btn" disabled={!draft.first_name.trim() && !draft.last_name.trim()} onClick={() => void create()}>
            Ajouter
          </button>
          {error && <span className="modal__error">{error}</span>}
        </div>
      )}
    </div>
  )
}

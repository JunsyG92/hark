import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createApi, type AnalysisStatusInfo, type CloudSettingsView, type LLMModelProfile, type LLMSettings, type ProfileDocument,
} from '../lib/api'

export function AnalysisSection() {
  const api = useMemo(() => createApi(window.hark.api), [])
  const [llm, setLlm] = useState<LLMSettings | null>(null)
  const [models, setModels] = useState<LLMModelProfile[]>([])
  const [status, setStatus] = useState<AnalysisStatusInfo | null>(null)
  const [model, setModel] = useState('')

  const refreshModels = useCallback(async () => {
    try {
      setModels(await api.llmModels())
    } catch {
      /* engine unreachable */
    }
  }, [api])

  useEffect(() => {
    let alive = true
    void api.llmSettings().then((s) => {
      if (!alive) return
      setLlm(s)
      setModel(s.model)
    }).catch(() => undefined)
    void refreshModels()
    const tick = () =>
      void api.analysisStatus().then((s) => {
        if (!alive) return
        setStatus((prev) => {
          if (prev?.pull.state === 'downloading' && s.pull.state !== 'downloading') void refreshModels()
          return s
        })
      }).catch(() => undefined)
    tick()
    const id = window.setInterval(tick, 2000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [api, refreshModels])

  async function patch(p: Partial<LLMSettings>) {
    try {
      const next = await api.patchLlmSettings(p)
      setLlm(next)
      setModel(next.model)
    } catch {
      /* rejected by the engine (out of range / invalid): keep previous value */
    }
  }

  if (!llm) return null
  const pulling = status?.pull.state === 'downloading'
  return (
    <fieldset className="detect">
      <legend>Analyse IA (résumé, décisions, tâches)</legend>
      <p className="modal__source">
        L’analyse tourne avec <strong>Ollama</strong> sur ta machine (aucune donnée ne sort). Elle découpe la transcription en
        blocs, résume chaque bloc puis fait une seule passe d’extraction ; une même transcription n’est jamais analysée deux fois.
        Les tâches trouvées arrivent dans « À valider » : rien n’est ajouté sans ton accord.
      </p>
      {status && (
        <p className={status.available ? 'modal__source' : 'modal__error'} data-testid="llm-status">
          {status.available
            ? `Prêt : ${status.provider} · ${status.model}`
            : `Indisponible : ${status.availability_error ?? 'inconnu'}`}
        </p>
      )}
      <div role="radiogroup" aria-label="Modèle Ollama" className="models">
        {models.map((m) => (
          <label key={m.id} className={`model${llm.model === m.ollama_model ? ' model--on' : ''}`}>
            <input type="radio" name="llm" checked={llm.model === m.ollama_model} onChange={() => void patch({ model: m.ollama_model })} />
            <span className="model__body">
              <strong>{m.label}</strong>
              {m.recommended && <span className="pill pill--mine">recommandé pour cette machine</span>}
              <span className="model__desc">{m.description}</span>
              <span className="model__desc"><code>{m.ollama_model}</code> · ≈ {m.download_gb} Go · {m.min_ram_gb} Go de RAM conseillés</span>
            </span>
            {m.installed ? (
              <span className="pill">installé ✓</span>
            ) : (
              <button type="button" className="btn" disabled={pulling} onClick={() => void api.pullLlm(m.ollama_model).then(() => api.analysisStatus().then(setStatus))}>
                {pulling && status?.pull.model === m.ollama_model ? 'Téléchargement…' : 'Télécharger'}
              </button>
            )}
          </label>
        ))}
      </div>
      {status?.pull.state === 'error' && <p className="modal__error">Téléchargement impossible : {status.pull.error}</p>}
      <label>
        Ou un autre modèle déjà installé dans Ollama
        <input value={model} maxLength={100} onChange={(e) => setModel(e.target.value)} onBlur={() => model.trim() && model.trim() !== llm.model && void patch({ model: model.trim() })} aria-label="Nom du modèle Ollama" />
      </label>
      <div className="modal__row">
        <label>
          Taille des blocs (tokens)
          <input type="number" min={500} max={6000} step={100} value={llm.chunk_tokens} onChange={(e) => e.target.value && void patch({ chunk_tokens: Number(e.target.value) })} />
        </label>
        <label>
          Budget par réunion (tokens)
          <input type="number" min={2000} max={500000} step={1000} value={llm.max_tokens_per_meeting} onChange={(e) => e.target.value && void patch({ max_tokens_per_meeting: Number(e.target.value) })} />
        </label>
      </div>
      <label className="checkbox">
        <input type="checkbox" checked={llm.auto_analyze} onChange={(e) => void patch({ auto_analyze: e.target.checked })} />
        Analyser automatiquement après chaque transcription
      </label>
      <ProfileEditor />
      <CloudBlock />
    </fieldset>
  )
}

function ProfileEditor() {
  const api = useMemo(() => createApi(window.hark.api), [])
  const [doc, setDoc] = useState<ProfileDocument | null>(null)
  const [text, setText] = useState('')
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    void api.profile().then((d) => {
      setDoc(d)
      setText(d.yaml)
    }).catch(() => undefined)
  }, [api])

  async function save() {
    try {
      const saved = await api.saveProfile(text)
      setDoc(saved)
      setMessage({ ok: true, text: 'Profil enregistré. Les tâches qui te concernent seront mises en avant.' })
    } catch (err) {
      setMessage({ ok: false, text: String((err as Error).message) })
    }
  }

  if (!doc) return null
  return (
    <div className="profile">
      <label>
        Ton profil (profile.yaml)
        <textarea className="mono" rows={9} spellCheck={false} value={text} onChange={(e) => setText(e.target.value)} aria-label="Profil YAML" />
      </label>
      {doc.error && <p className="modal__error">Fichier actuel invalide : {doc.error}</p>}
      {message && <p className={message.ok ? 'modal__source' : 'modal__error'}>{message.text}</p>}
      <div className="modal__actions">
        <button type="button" className="btn" onClick={() => void save()}>Enregistrer le profil</button>
      </div>
    </div>
  )
}

function CloudBlock() {
  const api = useMemo(() => createApi(window.hark.api), [])
  const [cloud, setCloud] = useState<CloudSettingsView | null>(null)
  const [key, setKey] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void api.cloudSettings().then(setCloud).catch(() => undefined)
  }, [api])

  async function patch(p: Partial<CloudSettingsView>) {
    try {
      setCloud(await api.patchCloudSettings(p))
      setError(null)
    } catch (err) {
      setError(String((err as Error).message))
    }
  }

  async function switchCloud(on: boolean) {
    try {
      if (on) {
        setCloud(await api.patchCloudSettings({ enabled: true }))
        await api.patchLlmSettings({ provider: 'cloud' })
      } else {
        await api.patchLlmSettings({ provider: 'ollama' })
        setCloud(await api.patchCloudSettings({ enabled: false }))
      }
      setError(null)
    } catch (err) {
      setError(String((err as Error).message))
    }
  }

  if (!cloud) return null
  return (
    <details className="cloud">
      <summary>Fournisseur cloud (désactivé par défaut)</summary>
      <p className="modal__error">
        Attention : activer le cloud envoie le <strong>texte des transcriptions</strong> à un service externe. Hark ne le fait
        jamais sans cette configuration explicite.
      </p>
      <label className="checkbox">
        <input type="checkbox" checked={cloud.acknowledged} onChange={(e) => void patch({ acknowledged: e.target.checked })} />
        Je comprends que le texte de mes réunions quittera cette machine
      </label>
      <label>URL de l’API (compatible OpenAI, https://…)
        <input value={cloud.base_url} onChange={(e) => setCloud({ ...cloud, base_url: e.target.value })} onBlur={() => void patch({ base_url: cloud.base_url })} />
      </label>
      <label>Modèle
        <input value={cloud.model} onChange={(e) => setCloud({ ...cloud, model: e.target.value })} onBlur={() => void patch({ model: cloud.model })} />
      </label>
      <label>Clé d’API {cloud.has_key ? '(enregistrée dans le gestionnaire d’identifiants)' : ''}
        <input type="password" value={key} autoComplete="off" onChange={(e) => setKey(e.target.value)} />
      </label>
      <div className="modal__actions">
        <button type="button" className="btn" disabled={key.length < 8} onClick={() => void api.saveCloudKey(key).then(() => { setKey(''); return api.cloudSettings().then(setCloud) })}>Enregistrer la clé</button>
        <label className="checkbox">
          <input type="checkbox" checked={cloud.enabled} disabled={!cloud.acknowledged || !cloud.has_key} onChange={(e) => void switchCloud(e.target.checked)} />
          Utiliser le cloud à la place d’Ollama
        </label>
      </div>
      {error && <p className="modal__error">{error}</p>}
    </details>
  )
}

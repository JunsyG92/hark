import { enc } from './meetings'
import type {
  Column,
  DetectionSettings,
  DetectionStatus,
  LLMModelProfile,
  LLMSettings,
  Meeting,
  ModelProfile,
  Person,
  Priority,
  RecordingSettings,
  RecordingStatus,
  SearchHit,
  Task,
  TranscriptionSettings,
  TranscriptSegment,
  Analysis,
  UserProfile,
} from './contracts.gen'

export type {
  Person,
  Analysis,
  LLMModelProfile,
  LLMSettings,
  UserProfile,
  Column,
  DetectionSettings,
  DetectionStatus,
  Meeting,
  ModelProfile,
  Priority,
  RecordingSettings,
  RecordingStatus,
  SearchHit,
  Task,
  TranscriptionSettings,
  TranscriptSegment,
}

export interface TaskDraft {
  title: string
  description?: string
  assignee?: string
  assignee_id?: string | null
  due?: string | null
  priority?: Priority
  column?: Column
}

export type TaskPatch = Partial<Pick<Task, 'title' | 'description' | 'assignee' | 'assignee_id' | 'due' | 'priority' | 'is_mine'>>

export interface PersonDraft {
  first_name: string
  last_name: string
  email: string
}

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly detail: unknown) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`)
  }
}

type Transport = (req: { method: string; path: string; body?: unknown }) => Promise<{ status: number; body: unknown }>

export function createApi(transport: Transport) {
  async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await transport({ method, path, body })
    if (res.status >= 400) {
      const detail = (res.body as { detail?: unknown } | null)?.detail ?? res.body
      throw new ApiError(res.status, detail)
    }
    return res.body as T
  }
  return {
    listTasks: () => call<Task[]>('GET', '/v1/tasks'),
    createTask: (draft: TaskDraft) => call<Task>('POST', '/v1/tasks', draft),
    updateTask: (id: string, patch: TaskPatch) => call<Task>('PATCH', `/v1/tasks/${encodeURIComponent(id)}`, patch),
    moveTask: (id: string, column: Column, index: number) =>
      call<Task>('POST', `/v1/tasks/${encodeURIComponent(id)}/move`, { column, index }),
    detectionStatus: () => call<DetectionStatus>('GET', '/v1/detection/status'),
    detectionSettings: () => call<DetectionSettings>('GET', '/v1/settings/detection'),
    patchDetectionSettings: (patch: Partial<DetectionSettings>) =>
      call<DetectionSettings>('PATCH', '/v1/settings/detection', patch),
    testDetectionPrompt: () => call<{ prompted: boolean }>('POST', '/v1/detection/test'),
    recordingStatus: () => call<RecordingStatus>('GET', '/v1/recording/status'),
    startRecording: (title = '') => call<Meeting>('POST', '/v1/recording/start', { title }),
    stopRecording: () => call<Meeting>('POST', '/v1/recording/stop'),
    recordingSettings: () => call<RecordingSettings>('GET', '/v1/settings/recording'),
    patchRecordingSettings: (patch: Partial<RecordingSettings>) =>
      call<RecordingSettings>('PATCH', '/v1/settings/recording', patch),
    listMeetings: () => call<Meeting[]>('GET', '/v1/meetings?limit=100'),
    renameMeeting: (id: string, title: string) => call<Meeting>('PATCH', `/v1/meetings/${enc(id)}`, { title }),
    deleteMeeting: (id: string) => call<null>('DELETE', `/v1/meetings/${enc(id)}`),
    transcript: (id: string) => call<TranscriptSegment[]>('GET', `/v1/meetings/${enc(id)}/transcript`),
    exportMarkdown: (id: string) => call<string>('GET', `/v1/meetings/${enc(id)}/export.md`),
    retranscribe: (id: string) => call<{ status: string }>('POST', `/v1/meetings/${enc(id)}/transcribe`),
    search: (q: string) => call<SearchHit[]>('GET', `/v1/search?q=${enc(q)}&limit=40`),
    meetingTasks: (id: string) => call<Task[]>('GET', `/v1/tasks?source=${enc(`meeting:${id}`)}`),
    models: () => call<ModelProfile[]>('GET', '/v1/models'),
    downloadModel: (profile: string) => call<{ status: string }>('POST', '/v1/models/download', { profile }),
    transcriptionSettings: () => call<TranscriptionSettings>('GET', '/v1/settings/transcription'),
    patchTranscriptionSettings: (patch: Partial<TranscriptionSettings>) =>
      call<TranscriptionSettings>('PATCH', '/v1/settings/transcription', patch),
    transcriptionStatus: () => call<TranscriptionStatusInfo>('GET', '/v1/transcription/status'),
    analysis: (id: string) => call<Analysis>('GET', `/v1/meetings/${enc(id)}/analysis`),
    analyze: (id: string, force = false) =>
      call<{ status: string }>('POST', `/v1/meetings/${enc(id)}/analyze${force ? '?force=true' : ''}`),
    llmSettings: () => call<LLMSettings>('GET', '/v1/settings/llm'),
    patchLlmSettings: (patch: Partial<LLMSettings>) => call<LLMSettings>('PATCH', '/v1/settings/llm', patch),
    llmModels: () => call<LLMModelProfile[]>('GET', '/v1/llm/models'),
    pullLlm: (model: string) => call<{ status: string }>('POST', '/v1/llm/pull', { model }),
    analysisStatus: () => call<AnalysisStatusInfo>('GET', '/v1/analysis/status'),
    profile: () => call<ProfileDocument>('GET', '/v1/profile'),
    saveProfile: (yaml: string) => call<ProfileDocument>('PUT', '/v1/profile', { yaml }),
    cloudSettings: () => call<CloudSettingsView>('GET', '/v1/settings/cloud'),
    patchCloudSettings: (patch: Partial<CloudSettingsView>) => call<CloudSettingsView>('PATCH', '/v1/settings/cloud', patch),
    saveCloudKey: (key: string) => call<null>('PUT', '/v1/settings/cloud/key', { key }),
    people: () => call<Person[]>('GET', '/v1/people'),
    createPerson: (p: PersonDraft) => call<Person>('POST', '/v1/people', p),
    updatePerson: (id: string, p: Partial<PersonDraft>) => call<Person>('PATCH', `/v1/people/${enc(id)}`, p),
    deletePerson: (id: string) => call<null>('DELETE', `/v1/people/${enc(id)}`),
    deleteTask: (id: string) => call<null>('DELETE', `/v1/tasks/${encodeURIComponent(id)}`),
  }
}

export interface TranscriptionStatusInfo {
  queue: string[]
  current_meeting_id: string | null
  progress: number
  model_installed: boolean
  download: { state: 'idle' | 'downloading' | 'done' | 'error'; profile: string | null; error: string | null }
}

export interface AnalysisStatusInfo {
  queue: string[]
  current_meeting_id: string | null
  provider: string
  model: string
  available: boolean
  availability_error: string | null
  pull: { state: 'idle' | 'downloading' | 'done' | 'error'; model: string | null; error: string | null }
}

export interface ProfileDocument {
  yaml: string
  profile: UserProfile | null
  error: string | null
}

export interface CloudSettingsView {
  enabled: boolean
  acknowledged: boolean
  base_url: string
  model: string
  has_key: boolean
}

export type HarkApi = ReturnType<typeof createApi>

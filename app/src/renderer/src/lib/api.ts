import { enc } from './meetings'
import type {
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
} from './contracts.gen'

export type {
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
  due?: string | null
  priority?: Priority
  column?: Column
}

export type TaskPatch = Partial<Pick<Task, 'title' | 'description' | 'assignee' | 'due' | 'priority' | 'is_mine'>>

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

export type HarkApi = ReturnType<typeof createApi>

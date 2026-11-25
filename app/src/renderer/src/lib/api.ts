import type { Column, DetectionSettings, DetectionStatus, Priority, Task } from './contracts.gen'

export type { Column, DetectionSettings, DetectionStatus, Priority, Task }

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
    deleteTask: (id: string) => call<null>('DELETE', `/v1/tasks/${encodeURIComponent(id)}`),
  }
}

export type HarkApi = ReturnType<typeof createApi>

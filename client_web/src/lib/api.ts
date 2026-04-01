import type { TaskStatus } from './statuses';

export interface Task {
  id: number;
  title: string;
  assignee_id: number | null;
  assignee_name: string | null;
  assignee_username: string | null;
  description: string;
  importance: number;
  estimated_effort: number;
  created_time: number;
  status: TaskStatus;
  tags: string[];
  blockers: number[];
  parent_task_id: number | null;
}

export interface User {
  id: number;
  external_id: string;
  username: string | null;
  display_name: string;
  report_to: number | null;
}

export type CommentType = 'TEXT' | 'METADATA_CHANGE' | 'EXECUTION_LOG';

export interface Comment {
  id: number;
  task_id: number;
  commenter_id: number | null;
  commenter_name: string | null;
  commenter_username: string | null;
  content: string;
  comment_type: CommentType;
  created_time: number;
}

export interface Tag {
  id: number;
  name: string;
}

export interface Board {
  id: number;
  name: string;
  description: string;
  created_time: number;
  archived: boolean;
}

export interface CreateTaskData {
  title: string;
  description?: string;
  importance?: number;
  estimated_effort?: number;
  assignee?: string | null;
  tags?: string[];
  blockers?: number[];
  parent_task_id?: number | null;
}

export interface EditTaskData {
  title?: string;
  description?: string;
  importance?: number;
  estimated_effort?: number;
  assignee?: string | null;
  assignee_id?: number | null;
  status?: TaskStatus;
  tags?: string[];
  blockers?: number[];
  parent_task_id?: number | null;
}

export interface CreateBoardData {
  name: string;
  description?: string;
}

const BASE_URL = '';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    let message = `API error ${res.status}: ${text}`;
    try {
      const json = JSON.parse(text);
      if (json.detail) message = json.detail;
    } catch {}
    throw new Error(message);
  }
  return res.json();
}

// --- Board API ---

export async function listBoards(includeArchived = false): Promise<Board[]> {
  const params = includeArchived ? '?include_archived=true' : '';
  return request<Board[]>(`/api/v1/boards${params}`);
}

export async function createBoard(data: CreateBoardData): Promise<Board> {
  return request<Board>('/api/v1/boards/new', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function editBoard(boardId: number, data: { name?: string; description?: string; archived?: boolean }): Promise<Board> {
  return request<Board>(`/api/v1/board/${boardId}/edit`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getBoard(id: number): Promise<Board> {
  return request<Board>(`/api/v1/board/${id}`);
}

// --- Task API (scoped to board) ---

export async function listTasks(boardId: number, filter?: string): Promise<Task[]> {
  const params = filter ? `?filter=${encodeURIComponent(filter)}` : '';
  return request<Task[]>(`/api/v1/board/${boardId}/tasks${params}`);
}

export async function createTask(boardId: number, data: CreateTaskData): Promise<Task> {
  return request<Task>(`/api/v1/board/${boardId}/tasks/new`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getTask(boardId: number, id: number): Promise<Task> {
  return request<Task>(`/api/v1/board/${boardId}/tasks/${id}`);
}

export async function editTask(boardId: number, id: number, data: EditTaskData, actorUsername?: string | null): Promise<Task> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (actorUsername) headers['X-Actor-Username'] = actorUsername;
  return request<Task>(`/api/v1/board/${boardId}/tasks/${id}/edit`, {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  });
}

export async function getComments(boardId: number, taskId: number): Promise<Comment[]> {
  return request<Comment[]>(`/api/v1/board/${boardId}/tasks/${taskId}/comments`);
}

export async function addComment(boardId: number, taskId: number, content: string, commenterUsername?: string | null): Promise<Comment> {
  const body: any = { content };
  if (commenterUsername != null) body.commenter = commenterUsername;
  return request<Comment>(`/api/v1/board/${boardId}/tasks/${taskId}/new_comment`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function listTags(boardId: number): Promise<Tag[]> {
  return request<Tag[]>(`/api/v1/board/${boardId}/tags`);
}

// --- SSE Events ---

export interface BoardEvent {
  type: 'task_created' | 'task_updated' | 'comment_added';
  data: any;
}

export function subscribeToBoardEvents(
  boardId: number,
  onEvent: (event: BoardEvent) => void,
  onStateChange?: (connected: boolean) => void,
): () => void {
  const url = `${BASE_URL}/api/v1/board/${boardId}/events`;
  const source = new EventSource(url);

  source.onopen = () => {
    onStateChange?.(true);
  };

  source.onmessage = (e) => {
    try {
      const event: BoardEvent = JSON.parse(e.data);
      onEvent(event);
    } catch {
      // ignore parse errors
    }
  };

  source.onerror = () => {
    onStateChange?.(false);
  };

  // Return cleanup function
  return () => {
    source.close();
    onStateChange?.(false);
  };
}

// --- User API (global) ---

export async function listUsers(): Promise<User[]> {
  return request<User[]>('/api/v1/users');
}

export async function createUser(data: { external_id: string; username?: string; display_name: string }): Promise<User> {
  return request<User>('/api/v1/users/new', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function editUser(id: number, data: { external_id?: string; username?: string; display_name?: string }): Promise<User> {
  return request<User>(`/api/v1/users/${id}/edit`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deleteUser(id: number): Promise<void> {
  await request(`/api/v1/users/${id}/delete`, { method: 'POST' });
}

// --- Attachment API ---

export interface Attachment {
  id: number;
  task_id: number;
  board_id: number;
  filename: string;
  original_name: string;
  content_type: string;
  size: number;
  uploader_id: number | null;
  created_time: number;
  comment_id: number | null;
}

export async function uploadFile(boardId: number, taskId: number, file: File): Promise<Attachment> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${BASE_URL}/api/v1/board/${boardId}/tasks/${taskId}/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function uploadCommentFile(boardId: number, taskId: number, commentId: number, file: File): Promise<Attachment> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${BASE_URL}/api/v1/board/${boardId}/tasks/${taskId}/comments/${commentId}/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function getAttachments(boardId: number, taskId: number): Promise<Attachment[]> {
  return request<Attachment[]>(`/api/v1/board/${boardId}/tasks/${taskId}/attachments`);
}

export async function deleteAttachment(attachmentId: number): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/v1/files/${attachmentId}`, { method: 'DELETE' });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
}

export function getFileUrl(attachmentId: number): string {
  return `${BASE_URL}/api/v1/files/${attachmentId}`;
}

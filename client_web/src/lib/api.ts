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
  text_comment_count: number;
}

export interface User {
  id: number;
  external_id: string;
  username: string | null;
  display_name: string;
  report_to: number | null;
  role: string | null;
  role_id: number | null;
  disabled: number;
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

let accessToken: string | null = localStorage.getItem('accessToken');

export function setAccessToken(token: string | null) {
  accessToken = token;
  if (token) localStorage.setItem('accessToken', token);
  else localStorage.removeItem('accessToken');
}

export function getAccessToken(): string | null {
  return accessToken;
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
  const mergedHeaders = { ...headers, ...(options?.headers as Record<string, string> || {}) };
  const res = await fetch(`${BASE_URL}${url}`, {
    ...options,
    headers: mergedHeaders,
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

export async function getMe(): Promise<User> {
  return request<User>('/api/v1/auth/me');
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

export async function getUnreadTaskIds(boardId: number): Promise<number[]> {
  return request<number[]>(`/api/v1/board/${boardId}/unread`);
}

export async function markTasksRead(boardId: number, taskIds: number[]): Promise<void> {
  await request(`/api/v1/board/${boardId}/mark-read`, {
    method: 'POST',
    body: JSON.stringify({ task_ids: taskIds }),
  });
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

export async function editTask(boardId: number, id: number, data: EditTaskData): Promise<Task> {
  return request<Task>(`/api/v1/board/${boardId}/tasks/${id}/edit`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getComments(boardId: number, taskId: number): Promise<Comment[]> {
  return request<Comment[]>(`/api/v1/board/${boardId}/tasks/${taskId}/comments`);
}

export async function addComment(boardId: number, taskId: number, content: string): Promise<Comment> {
  return request<Comment>(`/api/v1/board/${boardId}/tasks/${taskId}/new_comment`, {
    method: 'POST',
    body: JSON.stringify({ content }),
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
  const tokenParam = accessToken ? `?token=${encodeURIComponent(accessToken)}` : '';
  const url = `${BASE_URL}/api/v1/board/${boardId}/events${tokenParam}`;
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
  return request<User>('/api/v1/users', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function editUser(id: number, data: { external_id?: string; username?: string; display_name?: string; role?: string; disabled?: number }): Promise<User> {
  return request<User>(`/api/v1/users/${id}`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// --- Token API ---

export interface TokenInfo {
  id: number;
  user_id: number;
  label: string;
  created_time: number;
  last_used_time: number | null;
}

export interface TokenCreated {
  id: number;
  user_id: number;
  token: string;
  label: string;
  created_time: number;
}

export async function createToken(userId: number, label: string = ''): Promise<TokenCreated> {
  return request<TokenCreated>(`/api/v1/users/${userId}/tokens`, {
    method: 'POST',
    body: JSON.stringify({ label }),
  });
}

export async function listTokens(userId: number): Promise<TokenInfo[]> {
  return request<TokenInfo[]>(`/api/v1/users/${userId}/tokens`);
}

export async function revokeToken(userId: number, tokenId: number): Promise<void> {
  await request(`/api/v1/users/${userId}/tokens/${tokenId}/revoke`, { method: 'POST' });
}

// --- Role API ---

export interface RoleBoardPermission {
  board_id: number;
  actions: string[];
}

export interface Role {
  id: number;
  name: string;
  description: string;
  built_in: number;
  permissions: string[];
  board_permissions: RoleBoardPermission[];
}

export const GLOBAL_ACL_ACTIONS = [
  { id: 'boards.create', label: 'Create boards' },
  { id: 'users.manage', label: 'Manage users & roles' },
  { id: 'users.create_direct_report', label: 'Create direct reports' },
  { id: 'users.edit', label: 'Edit direct reports' },
];

export const BOARD_ACL_ACTIONS = [
  { id: 'boards.read', label: 'View board' },
  { id: 'boards.write', label: 'Edit board' },
  { id: 'tasks.read', label: 'View tasks & comments' },
  { id: 'tasks.create', label: 'Create tasks' },
  { id: 'tasks.edit', label: 'Edit tasks' },
  { id: 'tasks.post_comment', label: 'Post comments' },
];

export const ACL_ACTIONS = [...GLOBAL_ACL_ACTIONS, ...BOARD_ACL_ACTIONS];

export async function listRoles(): Promise<Role[]> {
  return request<Role[]>('/api/v1/roles');
}

export async function createRoleApi(data: { name: string; description?: string; permissions: string[] }): Promise<Role> {
  return request<Role>('/api/v1/roles', { method: 'POST', body: JSON.stringify(data) });
}

export async function editRoleApi(id: number, data: { name?: string; description?: string; permissions?: string[] }): Promise<Role> {
  return request<Role>(`/api/v1/roles/${id}`, { method: 'POST', body: JSON.stringify(data) });
}

export async function deleteRoleApi(id: number): Promise<void> {
  await request(`/api/v1/roles/${id}`, { method: 'DELETE' });
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

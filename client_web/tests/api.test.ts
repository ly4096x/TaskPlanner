import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  listTasks,
  createTask,
  getTask,
  editTask,
  getComments,
  addComment,
  listUsers,
  createUser,
  listTags,
  listBoards,
  createBoard,
  getBoard,
} from '../src/lib/api';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

function mockResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  };
}

beforeEach(() => {
  mockFetch.mockReset();
});

// --- Board API ---

describe('listBoards', () => {
  it('fetches /api/v1/boards', async () => {
    const boards = [{ id: 1, name: 'Alpha' }];
    mockFetch.mockResolvedValue(mockResponse(boards));

    const result = await listBoards();

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/boards', expect.objectContaining({
      headers: { 'Content-Type': 'application/json' },
    }));
    expect(result).toEqual(boards);
  });
});

describe('createBoard', () => {
  it('POSTs to /api/v1/boards/new', async () => {
    const board = { id: 1, name: 'Alpha', description: '', created_time: 123 };
    mockFetch.mockResolvedValue(mockResponse(board));

    const result = await createBoard({ name: 'Alpha' });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/boards/new', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ name: 'Alpha' }),
    }));
    expect(result).toEqual(board);
  });

  it('POSTs with description', async () => {
    const board = { id: 2, name: 'Beta', description: 'Desc', created_time: 456 };
    mockFetch.mockResolvedValue(mockResponse(board));

    await createBoard({ name: 'Beta', description: 'Desc' });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/boards/new', expect.objectContaining({
      body: JSON.stringify({ name: 'Beta', description: 'Desc' }),
    }));
  });
});

describe('getBoard', () => {
  it('fetches /api/v1/board/{id}', async () => {
    const board = { id: 3, name: 'Gamma', description: '', created_time: 789 };
    mockFetch.mockResolvedValue(mockResponse(board));

    const result = await getBoard(3);

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/board/3', expect.anything());
    expect(result).toEqual(board);
  });
});

// --- Task API (now with boardId) ---

describe('listTasks', () => {
  it('fetches /api/v1/board/{boardId}/tasks', async () => {
    const tasks = [{ id: 1, title: 'Test' }];
    mockFetch.mockResolvedValue(mockResponse(tasks));

    const result = await listTasks(1);

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/board/1/tasks', expect.objectContaining({
      headers: { 'Content-Type': 'application/json' },
    }));
    expect(result).toEqual(tasks);
  });

  it('passes filter as query param', async () => {
    mockFetch.mockResolvedValue(mockResponse([]));
    await listTasks(2, 'status:NEW');

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/board/2/tasks?filter=status%3ANEW',
      expect.anything(),
    );
  });
});

describe('createTask', () => {
  it('POSTs to /api/v1/board/{boardId}/tasks/new', async () => {
    const task = { id: 1, title: 'New' };
    mockFetch.mockResolvedValue(mockResponse(task));

    const result = await createTask(5, { title: 'New', importance: 75 });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/board/5/tasks/new', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ title: 'New', importance: 75 }),
    }));
    expect(result).toEqual(task);
  });
});

describe('getTask', () => {
  it('fetches /api/v1/board/{boardId}/tasks/{id}', async () => {
    const task = { id: 5, title: 'Detail' };
    mockFetch.mockResolvedValue(mockResponse(task));

    const result = await getTask(3, 5);

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/board/3/tasks/5', expect.anything());
    expect(result).toEqual(task);
  });
});

describe('editTask', () => {
  it('POSTs to /api/v1/board/{boardId}/tasks/{id}/edit', async () => {
    const task = { id: 3, title: 'Updated' };
    mockFetch.mockResolvedValue(mockResponse(task));

    const result = await editTask(2, 3, { title: 'Updated', status: 'STARTED' });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/board/2/tasks/3/edit', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ title: 'Updated', status: 'STARTED' }),
    }));
    expect(result).toEqual(task);
  });
});

describe('getComments', () => {
  it('fetches /api/v1/board/{boardId}/tasks/{id}/comments', async () => {
    const comments = [{ id: 1, content: 'hello' }];
    mockFetch.mockResolvedValue(mockResponse(comments));

    const result = await getComments(4, 2);

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/board/4/tasks/2/comments', expect.anything());
    expect(result).toEqual(comments);
  });
});

describe('addComment', () => {
  it('POSTs to /api/v1/board/{boardId}/tasks/{id}/new_comment', async () => {
    const comment = { id: 1, content: 'note' };
    mockFetch.mockResolvedValue(mockResponse(comment));

    const result = await addComment(6, 7, 'note');

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/board/6/tasks/7/new_comment', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ content: 'note' }),
    }));
    expect(result).toEqual(comment);
  });
});

describe('listTags', () => {
  it('fetches /api/v1/board/{boardId}/tags', async () => {
    const tags = [{ id: 1, name: 'bug' }];
    mockFetch.mockResolvedValue(mockResponse(tags));

    const result = await listTags(9);

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/board/9/tags', expect.anything());
    expect(result).toEqual(tags);
  });
});

// --- User API (global, unchanged) ---

describe('listUsers', () => {
  it('fetches /api/v1/users', async () => {
    const users = [{ id: 1, name: 'Alice' }];
    mockFetch.mockResolvedValue(mockResponse(users));

    const result = await listUsers();

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/users', expect.anything());
    expect(result).toEqual(users);
  });
});

describe('createUser', () => {
  it('POSTs to /api/v1/users/new', async () => {
    const user = { id: 1, name: 'Bob', external_id: 'bob1' };
    mockFetch.mockResolvedValue(mockResponse(user));

    const result = await createUser({ external_id: 'bob1', name: 'Bob' });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/users/new', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ external_id: 'bob1', name: 'Bob' }),
    }));
    expect(result).toEqual(user);
  });
});

describe('error handling', () => {
  it('throws on non-ok response', async () => {
    mockFetch.mockResolvedValue(mockResponse('Not Found', 404));

    await expect(listTasks(1)).rejects.toThrow('API error 404');
  });
});

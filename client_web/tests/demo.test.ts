// The GitHub Pages demo answers the API in-memory. These pin the parts a viewer
// would notice if they broke: the seeded board, the filter DSL the FilterBar
// sends, the 400 a malformed filter must produce (the UI shows it), and that a
// mutation is both persisted and broadcast to the fake EventSource.
import { beforeAll, describe, expect, it } from 'vitest';
import { installDemo } from '../src/lib/demo';
import fixture from '../src/lib/demo-data.json';

async function get<T>(path: string): Promise<{ status: number; body: T }> {
  const res = await fetch(path);
  return { status: res.status, body: (await res.json()) as T };
}

async function post<T>(path: string, body: unknown): Promise<{ status: number; body: T }> {
  const res = await fetch(path, { method: 'POST', body: JSON.stringify(body) });
  return { status: res.status, body: (await res.json()) as T };
}

type Task = { id: number; title: string; status: string; tags: string[]; text_comment_count: number; blockers: number[] };

beforeAll(() => {
  installDemo();
});

describe('demo mode API', () => {
  it('logs in as the first fixture user and serves the fixture boards', async () => {
    const me = await get<{ username: string }>('/api/v1/auth/me');
    expect(me.body.username).toBe(fixture.users[0].username);
    expect(localStorage.getItem('accessToken')).toBeTruthy();

    const boards = await get<{ name: string }[]>('/api/v1/boards');
    expect(boards.body.map((b) => b.name)).toEqual(fixture.boards.map((b) => b.name));
  });

  it('serves every fixture task on its board, with blockers resolved to ids', async () => {
    const tasks = await get<Task[]>('/api/v1/board/1/tasks');
    const onBoard1 = fixture.tasks.filter((t) => t.board === fixture.boards[0].name);
    expect(tasks.body).toHaveLength(onBoard1.length);
    const worker = tasks.body.find((t) => t.title.startsWith('Implement webhook delivery worker'))!;
    const design = tasks.body.find((t) => t.title.startsWith('Design the retry policy'))!;
    expect(worker.status).toBe('BLOCKED');
    expect(worker.blockers).toEqual([design.id]);
  });

  it('evaluates the filter DSL the way the server documents it', async () => {
    const all = (await get<Task[]>('/api/v1/board/1/tasks')).body;

    const r1 = await get<Task[]>('/api/v1/board/1/tasks?filter=' + encodeURIComponent('STATUS=NEW,TAGS=backend'));
    expect(r1.body.every((t) => t.status === 'NEW' && t.tags.includes('backend'))).toBe(true);
    expect(r1.body.length).toBe(all.filter((t) => t.status === 'NEW' && t.tags.includes('backend')).length);

    const r2 = await get<Task[]>('/api/v1/board/1/tasks?filter=' + encodeURIComponent('(status = DONE OR status=CANCELLED) AND NOT TAGS=research'));
    expect(r2.body.map((t) => t.status)).toEqual(['DONE']);

    const r3 = await get<Task[]>('/api/v1/board/1/tasks?filter=' + encodeURIComponent('TITLE~="webhook" AND IMPORTANCE>=40'));
    expect(r3.body.length).toBeGreaterThan(0);
    expect(r3.body.every((t) => t.title.toLowerCase().includes('webhook'))).toBe(true);

    const r4 = await get<Task[]>('/api/v1/board/1/tasks?filter=' + encodeURIComponent('CREATED_TIME>=-86400000'));
    expect(r4.body.length).toBe(all.length); // everything was created within the last 1000 days
  });

  it('rejects a malformed filter with the 400 the UI expects', async () => {
    const bad = await get<{ detail: string }>('/api/v1/board/1/tasks?filter=' + encodeURIComponent('STATUS=='));
    expect(bad.status).toBe(400);
    expect(bad.body.detail).toMatch(/^Invalid filter/);

    const unknown = await get<{ detail: string }>('/api/v1/board/1/tasks?filter=' + encodeURIComponent('COLOUR=red'));
    expect(unknown.status).toBe(400);
  });

  it('persists a comment, bumps the count, and broadcasts it on the board stream', async () => {
    const received: string[] = [];
    const es = new EventSource('/api/v1/board/1/events');
    es.onmessage = (e) => received.push(String(e.data));
    await new Promise((r) => setTimeout(r, 0));

    const before = (await get<Task[]>('/api/v1/board/1/tasks')).body[0];
    const posted = await post<{ id: number; comment_type: string }>(`/api/v1/board/1/tasks/${before.id}/new_comment`, { content: 'hello from the test' });
    expect(posted.status).toBe(201);
    expect(posted.body.comment_type).toBe('TEXT');

    const after = (await get<Task>(`/api/v1/board/1/tasks/${before.id}`)).body;
    expect(after.text_comment_count).toBe(before.text_comment_count + 1);

    await new Promise((r) => setTimeout(r, 0));
    expect(received.some((d) => JSON.parse(d).type === 'comment_added')).toBe(true);
    es.close();
  });

  it('refuses BLOCKED without a blocker, like the server, and records edits as metadata comments', async () => {
    const created = await post<Task>('/api/v1/board/2/tasks/new', { title: 'demo edit target' });
    expect(created.status).toBe(201);

    const refused = await post<{ detail: string }>(`/api/v1/board/2/tasks/${created.body.id}/edit`, { status: 'BLOCKED' });
    expect(refused.status).toBe(422);

    const moved = await post<Task>(`/api/v1/board/2/tasks/${created.body.id}/edit`, { status: 'STARTED', importance: 77 });
    expect(moved.body.status).toBe('STARTED');
    const comments = (await get<{ comment_type: string }[]>(`/api/v1/board/2/tasks/${created.body.id}/comments`)).body;
    expect(comments.some((c) => c.comment_type === 'METADATA_CHANGE')).toBe(true);
  });

  it('404s a task looked up on the wrong board, naming the right one', async () => {
    const r = await get<{ detail: string }>('/api/v1/board/2/tasks/1');
    expect(r.status).toBe(404);
    expect(r.body.detail).toMatch(/board 1/);
  });

  it('leaves non-API fetches alone', async () => {
    // jsdom has no network; the real fetch rejecting proves the call was passed through
    await expect(fetch('/favicon.svg')).rejects.toBeTruthy();
  });
});

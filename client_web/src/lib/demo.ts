// Frontend-only demo mode for GitHub Pages.
//
// The real app talks to the FastAPI server through `fetch` (api.ts) and listens on
// an EventSource for board events. When built with VITE_DEMO=1 this module replaces
// both with an in-memory implementation of the same REST surface, seeded from
// demo-data.json — so the UI code is untouched and the demo is genuinely
// interactive: create and edit tasks, comment, filter, drag between columns.
// Nothing persists; a reload resets to the fixture.
//
// The filter DSL (`STATUS=NEW AND TAGS=bug`, see the taskplanner skill) is
// evaluated here with a small recursive-descent parser covering the documented
// grammar, so the FilterBar behaves as it does against the real server, including
// the 400 on a malformed filter.

import fixture from './demo-data.json';

type Json = Record<string, unknown>;

interface DemoUser {
  id: number;
  external_id: string;
  username: string;
  display_name: string;
  report_to: number | null;
  role: string;
  role_id: number;
  disabled: number;
}

interface DemoTask {
  id: number;
  board_id: number;
  title: string;
  assignee_id: number | null;
  assignee_name: string | null;
  assignee_username: string | null;
  description: string;
  importance: number;
  estimated_effort: number;
  created_time: number;
  last_activity_time: number;
  status: string;
  tags: string[];
  blockers: number[];
  parent_task_id: number | null;
  creator_id: number | null;
  text_comment_count: number;
}

interface DemoComment {
  id: number;
  task_id: number;
  commenter_id: number | null;
  commenter_name: string | null;
  commenter_username: string | null;
  content: string;
  comment_type: 'TEXT' | 'METADATA_CHANGE' | 'EXECUTION_LOG';
  created_time: number;
}

interface DemoBoard {
  id: number;
  name: string;
  description: string;
  created_time: number;
  archived: boolean;
}

const HOUR = 3600;
const DAY = 24 * HOUR;

// ---------------------------------------------------------------------------
// State, built once from the fixture
// ---------------------------------------------------------------------------

const now = () => Math.floor(Date.now() / 1000);

const roles = [
  { id: 1, name: 'admin', description: 'Built-in administrator', built_in: 1, permissions: [], board_permissions: [] },
  {
    id: 2,
    name: 'contributor',
    description: 'Can read and edit every board',
    built_in: 0,
    permissions: ['boards.read', 'boards.write', 'tasks.read', 'tasks.create', 'tasks.edit', 'tasks.post_comment'],
    board_permissions: [],
  },
];

const users: DemoUser[] = fixture.users.map((u, i) => ({
  id: i + 1,
  external_id: u.external_id,
  username: u.username,
  display_name: u.display_name,
  report_to: null,
  role: u.role === 'admin' ? 'admin' : 'contributor',
  role_id: u.role === 'admin' ? 1 : 2,
  disabled: 0,
}));
const me = users[0];

const t0 = now();
const boards: DemoBoard[] = fixture.boards.map((b, i) => ({
  id: i + 1,
  name: b.name,
  description: b.description ?? '',
  created_time: t0 - 30 * DAY + i * DAY,
  archived: false,
}));

const userByName = (name: string | null | undefined) =>
  name ? users.find((u) => u.username === name) ?? null : null;
const boardByName = (name: string) => boards.find((b) => b.name === name)!;

const tasks: DemoTask[] = [];
const comments: DemoComment[] = [];
let nextTaskId = 1;
let nextCommentId = 1;

// Spread creation over the last two weeks so relative timestamps look lived-in,
// newest last so ids and time agree.
fixture.tasks.forEach((t, i) => {
  const n = fixture.tasks.length;
  const created = t0 - (n - i) * (14 * DAY) / n - (i % 3) * HOUR;
  const assignee = userByName(t.assignee);
  const task: DemoTask = {
    id: nextTaskId++,
    board_id: boardByName(t.board).id,
    title: t.title,
    assignee_id: assignee?.id ?? null,
    assignee_name: assignee?.display_name ?? null,
    assignee_username: assignee?.username ?? null,
    description: t.description ?? '',
    importance: t.importance ?? 0,
    estimated_effort: t.estimated_effort ?? 0,
    created_time: created,
    last_activity_time: created,
    status: t.status,
    tags: [...(t.tags ?? [])],
    blockers: (t.blockers_by_title ?? []).map((title) => tasks.find((x) => x.title === title)!.id),
    parent_task_id: t.parent_by_title ? tasks.find((x) => x.title === t.parent_by_title)!.id : null,
    creator_id: me.id,
    text_comment_count: 0,
  };
  tasks.push(task);
  (t.comments ?? []).forEach((c, j) => {
    const by = userByName(c.by);
    const when = created + (j + 1) * 5 * HOUR;
    comments.push({
      id: nextCommentId++,
      task_id: task.id,
      commenter_id: by?.id ?? null,
      commenter_name: by?.display_name ?? null,
      commenter_username: by?.username ?? null,
      content: c.text,
      comment_type: 'TEXT',
      created_time: when,
    });
    task.text_comment_count += 1;
    task.last_activity_time = Math.max(task.last_activity_time, when);
  });
});

// ---------------------------------------------------------------------------
// Filter DSL
// ---------------------------------------------------------------------------

class FilterError extends Error {}

type Tok = { kind: 'lp' | 'rp' | 'and' | 'or' | 'not' | 'word' | 'op' | 'str'; text: string };

function tokenize(src: string): Tok[] {
  const toks: Tok[] = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (/\s/.test(c)) { i++; continue; }
    if (c === '(') { toks.push({ kind: 'lp', text: c }); i++; continue; }
    if (c === ')') { toks.push({ kind: 'rp', text: c }); i++; continue; }
    if (c === ',') { toks.push({ kind: 'and', text: ',' }); i++; continue; }
    if (c === '"') {
      const end = src.indexOf('"', i + 1);
      if (end < 0) throw new FilterError('unterminated quoted value');
      toks.push({ kind: 'str', text: src.slice(i + 1, end) });
      i = end + 1;
      continue;
    }
    const op = src.slice(i).match(/^(~=|>=|<=|!=|=|>|<)/);
    if (op) { toks.push({ kind: 'op', text: op[1] }); i += op[1].length; continue; }
    const word = src.slice(i).match(/^[^\s(),"~=<>!]+/);
    if (!word) throw new FilterError(`unexpected character ${JSON.stringify(c)}`);
    const w = word[0];
    const upper = w.toUpperCase();
    if (upper === 'AND') toks.push({ kind: 'and', text: w });
    else if (upper === 'OR') toks.push({ kind: 'or', text: w });
    else if (upper === 'NOT') toks.push({ kind: 'not', text: w });
    else toks.push({ kind: 'word', text: w });
    i += w.length;
  }
  return toks;
}

type Pred = (t: DemoTask) => boolean;

const LIST_FIELDS = new Set(['TAGS', 'BLOCKERS']);
const NUM_FIELDS = new Set(['ID', 'IMPORTANCE', 'ESTIMATED_EFFORT', 'CREATED_TIME', 'PARENT']);
const FIELDS = new Set(['ID', 'TITLE', 'STATUS', 'DESCRIPTION', 'ASSIGNEE', 'IMPORTANCE', 'ESTIMATED_EFFORT', 'CREATED_TIME', 'TAGS', 'BLOCKERS', 'PARENT']);

function fieldValue(t: DemoTask, f: string): unknown {
  switch (f) {
    case 'ID': return t.id;
    case 'TITLE': return t.title;
    case 'STATUS': return t.status;
    case 'DESCRIPTION': return t.description;
    case 'ASSIGNEE': return t.assignee_username ?? '';
    case 'IMPORTANCE': return t.importance;
    case 'ESTIMATED_EFFORT': return t.estimated_effort;
    case 'CREATED_TIME': return t.created_time;
    case 'TAGS': return t.tags;
    case 'BLOCKERS': return t.blockers;
    case 'PARENT': return t.parent_task_id ?? 0;
  }
  return undefined;
}

function compare(field: string, op: string, raw: string): Pred {
  if (LIST_FIELDS.has(field)) {
    if (op !== '=' && op !== '!=') throw new FilterError(`operator ${op} not valid for ${field}`);
    const want = field === 'BLOCKERS' ? Number(raw) : raw.toLowerCase();
    return (t) => {
      const list = (fieldValue(t, field) as (string | number)[]).map((v) => (typeof v === 'string' ? v.toLowerCase() : v));
      const has = list.includes(want);
      return op === '=' ? has : !has;
    };
  }
  if (NUM_FIELDS.has(field)) {
    let want = Number(raw);
    if (field === 'CREATED_TIME' && /^[+-]/.test(raw)) want = now() + Number(raw);
    if (Number.isNaN(want)) throw new FilterError(`${field} needs a number, got ${JSON.stringify(raw)}`);
    return (t) => {
      const v = fieldValue(t, field) as number;
      switch (op) {
        case '=': return v === want;
        case '!=': return v !== want;
        case '>': return v > want;
        case '<': return v < want;
        case '>=': return v >= want;
        case '<=': return v <= want;
        case '~=': return String(v).includes(raw);
      }
      return false;
    };
  }
  const want = raw.toLowerCase();
  return (t) => {
    const v = String(fieldValue(t, field) ?? '').toLowerCase();
    switch (op) {
      case '=': return v === want;
      case '!=': return v !== want;
      case '~=': return v.includes(want);
      case '>': return v > want;
      case '<': return v < want;
      case '>=': return v >= want;
      case '<=': return v <= want;
    }
    return false;
  };
}

function parseFilter(src: string): Pred {
  const toks = tokenize(src);
  let pos = 0;
  const peek = () => toks[pos];
  const take = () => toks[pos++];

  function primary(): Pred {
    const t = take();
    if (!t) throw new FilterError('unexpected end of filter');
    if (t.kind === 'lp') {
      const inner = orExpr();
      if (take()?.kind !== 'rp') throw new FilterError('missing )');
      return inner;
    }
    if (t.kind === 'not') {
      const inner = primary();
      return (x) => !inner(x);
    }
    if (t.kind !== 'word') throw new FilterError(`unexpected ${JSON.stringify(t.text)}`);
    const field = t.text.toUpperCase();
    if (!FIELDS.has(field)) throw new FilterError(`unknown field ${t.text}`);
    const op = take();
    if (!op || op.kind !== 'op') throw new FilterError(`expected operator after ${t.text}`);
    const val = take();
    if (!val || (val.kind !== 'word' && val.kind !== 'str')) throw new FilterError(`expected value after ${op.text}`);
    return compare(field, op.text, val.text);
  }
  function andExpr(): Pred {
    let left = primary();
    while (peek()?.kind === 'and') {
      take();
      const right = primary();
      const l = left;
      left = (x) => l(x) && right(x);
    }
    return left;
  }
  function orExpr(): Pred {
    let left = andExpr();
    while (peek()?.kind === 'or') {
      take();
      const right = andExpr();
      const l = left;
      left = (x) => l(x) || right(x);
    }
    return left;
  }
  const pred = orExpr();
  if (pos !== toks.length) throw new FilterError(`unexpected ${JSON.stringify(toks[pos].text)}`);
  return pred;
}

// ---------------------------------------------------------------------------
// Board events: a fake EventSource so the "Live" indicator is honest — mutations
// made in this tab are broadcast to it exactly as the server would.
// ---------------------------------------------------------------------------

const openSources = new Map<number, Set<DemoEventSource>>();

class DemoEventSource {
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  readyState = 0;
  private boardId: number;
  constructor(url: string) {
    const m = String(url).match(/\/board\/(\d+)\/events/);
    this.boardId = m ? Number(m[1]) : 0;
    if (!openSources.has(this.boardId)) openSources.set(this.boardId, new Set());
    openSources.get(this.boardId)!.add(this);
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.(new Event('open'));
    }, 0);
  }
  close() {
    this.readyState = 2;
    openSources.get(this.boardId)?.delete(this);
  }
  addEventListener() {}
  removeEventListener() {}
}

function broadcast(boardId: number, type: string, data: unknown) {
  const payload = JSON.stringify({ type, data });
  for (const s of openSources.get(boardId) ?? []) {
    setTimeout(() => s.onmessage?.(new MessageEvent('message', { data: payload })), 0);
  }
}

// ---------------------------------------------------------------------------
// Routing
// ---------------------------------------------------------------------------

class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function requireBoard(id: number): DemoBoard {
  const b = boards.find((x) => x.id === id);
  if (!b) throw new HttpError(404, 'Board not found');
  return b;
}

function requireTask(boardId: number, id: number): DemoTask {
  const t = tasks.find((x) => x.id === id);
  if (!t) throw new HttpError(404, 'Task not found');
  if (t.board_id !== boardId) throw new HttpError(404, `Task ${id} lives on board ${t.board_id}, not ${boardId}`);
  return t;
}

function applyTaskEdit(t: DemoTask, body: Json) {
  const before = { ...t };
  if (typeof body.title === 'string') t.title = body.title;
  if (typeof body.description === 'string') t.description = body.description;
  if (typeof body.importance === 'number') t.importance = body.importance;
  if (typeof body.estimated_effort === 'number') t.estimated_effort = body.estimated_effort;
  if ('assignee' in body || 'assignee_id' in body) {
    const u =
      'assignee_id' in body
        ? users.find((x) => x.id === body.assignee_id) ?? null
        : userByName(body.assignee as string | null);
    t.assignee_id = u?.id ?? null;
    t.assignee_name = u?.display_name ?? null;
    t.assignee_username = u?.username ?? null;
  }
  if (Array.isArray(body.tags)) t.tags = body.tags.map(String);
  if (Array.isArray(body.blockers)) t.blockers = body.blockers.map(Number);
  if ('parent_task_id' in body) t.parent_task_id = (body.parent_task_id as number | null) ?? null;
  if (typeof body.status === 'string' && body.status !== t.status) {
    if (body.status === 'BLOCKED' && t.blockers.length === 0) {
      throw new HttpError(422, 'BLOCKED requires at least one blocker');
    }
    t.status = body.status;
  }
  const changed = Object.keys(before).filter((k) => JSON.stringify((before as Json)[k]) !== JSON.stringify((t as unknown as Json)[k]));
  if (changed.length) {
    t.last_activity_time = now();
    comments.push({
      id: nextCommentId++,
      task_id: t.id,
      commenter_id: me.id,
      commenter_name: me.display_name,
      commenter_username: me.username,
      content: changed.map((k) => `${k}: ${JSON.stringify((before as Json)[k])} → ${JSON.stringify((t as unknown as Json)[k])}`).join('\n'),
      comment_type: 'METADATA_CHANGE',
      created_time: t.last_activity_time,
    });
  }
}

async function route(method: string, path: string, query: URLSearchParams, body: Json | null): Promise<Response> {
  let m: RegExpMatchArray | null;

  if (path === '/api/v1/auth/me') return json(me);

  if (path === '/api/v1/boards') {
    const all = query.get('include_archived') === 'true';
    return json(boards.filter((b) => all || !b.archived));
  }
  if (path === '/api/v1/boards/new' && method === 'POST') {
    const b: DemoBoard = {
      id: boards.length + 1,
      name: String(body?.name ?? 'Untitled'),
      description: String(body?.description ?? ''),
      created_time: now(),
      archived: false,
    };
    boards.push(b);
    return json(b, 201);
  }
  if ((m = path.match(/^\/api\/v1\/board\/(\d+)$/))) return json(requireBoard(Number(m[1])));
  if ((m = path.match(/^\/api\/v1\/board\/(\d+)\/edit$/)) && method === 'POST') {
    const b = requireBoard(Number(m[1]));
    if (typeof body?.name === 'string') b.name = body.name;
    if (typeof body?.description === 'string') b.description = body.description;
    if (typeof body?.archived === 'boolean') b.archived = body.archived;
    return json(b);
  }

  if ((m = path.match(/^\/api\/v1\/board\/(\d+)\/tasks$/))) {
    const bid = requireBoard(Number(m[1])).id;
    let list = tasks.filter((t) => t.board_id === bid);
    const f = query.get('filter');
    if (f) {
      try {
        const pred = parseFilter(f);
        list = list.filter(pred);
      } catch (e) {
        if (e instanceof FilterError) throw new HttpError(400, `Invalid filter: ${e.message}`);
        throw e;
      }
    }
    return json(list);
  }
  if ((m = path.match(/^\/api\/v1\/board\/(\d+)\/unread$/))) return json([]);
  if ((m = path.match(/^\/api\/v1\/board\/(\d+)\/mark-read$/))) return json({ ok: true });
  if ((m = path.match(/^\/api\/v1\/board\/(\d+)\/tags$/))) {
    const bid = requireBoard(Number(m[1])).id;
    const names = [...new Set(tasks.filter((t) => t.board_id === bid).flatMap((t) => t.tags))].sort();
    return json(names.map((name, i) => ({ id: i + 1, name })));
  }
  if ((m = path.match(/^\/api\/v1\/board\/(\d+)\/tasks\/new$/)) && method === 'POST') {
    const bid = requireBoard(Number(m[1])).id;
    const t: DemoTask = {
      id: nextTaskId++,
      board_id: bid,
      title: String(body?.title ?? 'Untitled'),
      assignee_id: null, assignee_name: null, assignee_username: null,
      description: '', importance: 0, estimated_effort: 0,
      created_time: now(), last_activity_time: now(),
      status: 'NEW', tags: [], blockers: [], parent_task_id: null,
      creator_id: me.id, text_comment_count: 0,
    };
    tasks.push(t);
    applyTaskEdit(t, body ?? {});
    broadcast(bid, 'task_created', t);
    return json(t, 201);
  }
  if ((m = path.match(/^\/api\/v1\/board\/(\d+)\/tasks\/(\d+)$/))) {
    return json(requireTask(Number(m[1]), Number(m[2])));
  }
  if ((m = path.match(/^\/api\/v1\/board\/(\d+)\/tasks\/(\d+)\/edit$/)) && method === 'POST') {
    const t = requireTask(Number(m[1]), Number(m[2]));
    applyTaskEdit(t, body ?? {});
    broadcast(t.board_id, 'task_updated', t);
    return json(t);
  }
  if ((m = path.match(/^\/api\/v1\/board\/(\d+)\/tasks\/(\d+)\/comments$/))) {
    const t = requireTask(Number(m[1]), Number(m[2]));
    return json(comments.filter((c) => c.task_id === t.id));
  }
  if ((m = path.match(/^\/api\/v1\/board\/(\d+)\/tasks\/(\d+)\/new_comment$/)) && method === 'POST') {
    const t = requireTask(Number(m[1]), Number(m[2]));
    const c: DemoComment = {
      id: nextCommentId++,
      task_id: t.id,
      commenter_id: me.id,
      commenter_name: me.display_name,
      commenter_username: me.username,
      content: String(body?.content ?? ''),
      comment_type: 'TEXT',
      created_time: now(),
    };
    comments.push(c);
    t.text_comment_count += 1;
    t.last_activity_time = c.created_time;
    broadcast(t.board_id, 'comment_added', c);
    return json(c, 201);
  }
  if ((m = path.match(/^\/api\/v1\/board\/(\d+)\/tasks\/(\d+)\/attachments$/))) return json([]);
  if (path.includes('/upload')) throw new HttpError(400, 'Demo mode: file uploads are disabled');
  if ((m = path.match(/^\/api\/v1\/files\/(\d+)$/))) return json({ ok: true });

  if (path === '/api/v1/users') {
    if (method === 'POST') {
      const u: DemoUser = {
        id: users.length + 1,
        external_id: String(body?.external_id ?? ''),
        username: (body?.username as string) ?? null!,
        display_name: String(body?.display_name ?? ''),
        report_to: null, role: 'contributor', role_id: 2, disabled: 0,
      };
      users.push(u);
      return json(u, 201);
    }
    return json(users);
  }
  if ((m = path.match(/^\/api\/v1\/users\/(\d+)$/)) && method === 'POST') {
    const u = users.find((x) => x.id === Number(m![1]));
    if (!u) throw new HttpError(404, 'User not found');
    for (const k of ['external_id', 'username', 'display_name', 'role'] as const) {
      if (typeof body?.[k] === 'string') (u as unknown as Json)[k] = body[k];
    }
    if (typeof body?.disabled === 'number') u.disabled = body.disabled;
    if (typeof body?.role === 'string') u.role_id = roles.find((r) => r.name === body.role)?.id ?? u.role_id;
    return json(u);
  }
  if ((m = path.match(/^\/api\/v1\/users\/(\d+)\/tokens$/))) {
    if (method === 'POST') {
      return json({ id: 1, user_id: Number(m[1]), token: 'demo_token_not_real', label: String(body?.label ?? ''), created_time: now() }, 201);
    }
    return json([]);
  }
  if (path.match(/^\/api\/v1\/users\/\d+\/tokens\/\d+\/revoke$/)) return json({ ok: true });

  if (path === '/api/v1/roles') {
    if (method === 'POST') {
      const r = { id: roles.length + 1, name: String(body?.name ?? ''), description: String(body?.description ?? ''), built_in: 0, permissions: (body?.permissions as string[]) ?? [], board_permissions: [] };
      roles.push(r);
      return json(r, 201);
    }
    return json(roles);
  }
  if ((m = path.match(/^\/api\/v1\/roles\/(\d+)$/))) {
    const r = roles.find((x) => x.id === Number(m![1]));
    if (!r) throw new HttpError(404, 'Role not found');
    if (method === 'DELETE') {
      if (r.built_in) throw new HttpError(403, 'Built-in role');
      roles.splice(roles.indexOf(r), 1);
      return json({ ok: true });
    }
    if (method === 'POST') {
      if (typeof body?.name === 'string') r.name = body.name;
      if (typeof body?.description === 'string') r.description = body.description;
      if (Array.isArray(body?.permissions)) r.permissions = body.permissions.map(String);
    }
    return json(r);
  }

  throw new HttpError(404, `Demo mode: no handler for ${method} ${path}`);
}

// ---------------------------------------------------------------------------
// Install
// ---------------------------------------------------------------------------

export function installDemo() {
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, window.location.href);
    if (!url.pathname.startsWith('/api/v1/')) return realFetch(input, init);
    const method = (init?.method ?? 'GET').toUpperCase();
    let body: Json | null = null;
    if (typeof init?.body === 'string') {
      try { body = JSON.parse(init.body); } catch { body = null; }
    }
    try {
      return await route(method, url.pathname, url.searchParams, body);
    } catch (e) {
      if (e instanceof HttpError) return json({ detail: e.message }, e.status);
      throw e;
    }
  };
  (window as unknown as { EventSource: unknown }).EventSource = DemoEventSource;
  // The app auto-logs-in from a stored token; any value works against the demo.
  if (!localStorage.getItem('accessToken')) localStorage.setItem('accessToken', 'demo');

  const banner = document.createElement('div');
  banner.textContent = 'Demo — fictional data, lives in this tab only, resets on reload.';
  banner.style.cssText =
    'position:fixed;bottom:12px;right:12px;z-index:9999;padding:6px 10px;border-radius:6px;' +
    'font:12px/1.4 system-ui,sans-serif;background:#1f2937;color:#f9fafb;opacity:.85;pointer-events:none';
  document.body.appendChild(banner);
}

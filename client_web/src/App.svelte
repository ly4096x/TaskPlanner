<script lang="ts">
  import { listTasks, listBoards, editBoard, editTask, subscribeToBoardEvents, getMe, setAccessToken, getAccessToken, getUnreadTaskIds, markTasksRead, type Task, type Board, type BoardEvent } from './lib/api';
  import BoardSidebar from './components/BoardSidebar.svelte';
  import ViewToggle from './components/ViewToggle.svelte';
  import TaskList from './components/TaskList.svelte';
  import TaskGrid from './components/TaskGrid.svelte';
  import TaskDetail from './components/TaskDetail.svelte';
  import TaskForm from './components/TaskForm.svelte';
  import FilterBar from './components/FilterBar.svelte';
  import ThemeToggle from './components/ThemeToggle.svelte';
  import UsersPage from './components/UsersPage.svelte';
  import UserIdentity from './components/UserIdentity.svelte';
  import { listUsers, type User } from './lib/api';

  // --- URL state ---
  function readURL(): URLSearchParams {
    return new URLSearchParams(window.location.search);
  }

  function writeURL() {
    const p = new URLSearchParams();
    if (selectedBoard) p.set('board', String(selectedBoard.id));
    if (view !== 'list') p.set('view', view);
    if (sortStr) p.set('sort', sortStr);
    else if (sortField !== 'id') p.set('sortField', sortField);
    if (sortDir !== 'asc') p.set('dir', sortDir);
    if (filterStr) p.set('filter', filterStr);
    const qs = p.toString();
    const url = qs ? `?${qs}` : window.location.pathname;
    window.history.replaceState(null, '', url);
  }

  function initFromURL() {
    const p = readURL();
    return {
      boardId: p.has('board') ? Number(p.get('board')) : null,
      view: (p.get('view') === 'card' ? 'card' : 'list') as 'list' | 'card',
      sortField: p.get('sortField') || 'id',
      sortDir: (p.get('dir') === 'desc' ? 'desc' : 'asc') as 'asc' | 'desc',
      filter: p.get('filter') || '',
      sort: p.get('sort') || '',
    };
  }

  const urlState = initFromURL();

  let view: 'list' | 'card' = $state(urlState.view);
  let tasks: Task[] = $state([]);
  let unreadTaskIds: Set<number> = $state(new Set());
  let selectedTask: Task | null = $state(null);
  let showForm = $state(false);
  let loading = $state(true);
  let error = $state('');
  let filterStr = $state(urlState.filter);
  let sortStr = $state(urlState.sort || '');
  let sortField: string = $state(urlState.sortField);
  let sortDir: 'asc' | 'desc' = $state(urlState.sortDir);
  let urlBoardId: number | null = urlState.boardId;

  let boards: Board[] = $state([]);
  let selectedBoard: Board | null = $state(null);
  let boardsLoading = $state(true);
  let sidebarCollapsed = $state(window.innerWidth <= 768);
  let showUsers = $state(false);
  let showArchivedBoards = $state(false);
  let editingBoardName = $state(false);
  let editBoardNameValue = $state('');
  let currentUser: User | null = $state(null);
  let authChecked = $state(false);
  let loginToken = $state('');
  let loginError = $state('');
  let loginLoading = $state(false);

  // Auto-login from stored token on startup
  async function checkAuth() {
    const token = getAccessToken();
    if (token) {
      try {
        currentUser = await getMe();
      } catch {
        setAccessToken(null);
      }
    }
    authChecked = true;
  }

  async function handleLogin() {
    const token = loginToken.trim();
    if (!token) { loginError = 'Token required'; return; }
    loginError = '';
    loginLoading = true;
    try {
      setAccessToken(token);
      currentUser = await getMe();
      loginToken = '';
      loadBoards().then(() => {
        loadTasks();
        if (selectedBoard) setupSSE(selectedBoard.id);
      });
    } catch {
      setAccessToken(null);
      loginError = 'Invalid or expired token';
    } finally {
      loginLoading = false;
    }
  }

  function handleLogout() {
    setAccessToken(null);
    currentUser = null;
  }

  checkAuth().then(() => {
    if (currentUser) {
      loadBoards().then(() => {
        loadTasks();
        if (selectedBoard) setupSSE(selectedBoard.id);
      });
    }
  });

  let autoUpdate = $state(localStorage.getItem('autoUpdate') !== 'false');
  let sseConnected = $state(true);
  let unsubscribeEvents: (() => void) | null = null;

  function toggleAutoUpdate() {
    autoUpdate = !autoUpdate;
    localStorage.setItem('autoUpdate', String(autoUpdate));
    if (autoUpdate && selectedBoard) {
      setupSSE(selectedBoard.id);
    } else if (!autoUpdate && unsubscribeEvents) {
      unsubscribeEvents();
      unsubscribeEvents = null;
      sseConnected = false;
    }
  }

  function setupSSE(boardId: number) {
    if (!autoUpdate) return;
    if (unsubscribeEvents) unsubscribeEvents();
    unsubscribeEvents = subscribeToBoardEvents(boardId, (event: BoardEvent) => {
      if (event.type === 'task_created') {
        const newTask = event.data as Task;
        if (!tasks.find(t => t.id === newTask.id)) {
          tasks = [newTask, ...tasks];
        }
      } else if (event.type === 'task_updated') {
        const updated = event.data as Task;
        tasks = tasks.map(t => t.id === updated.id ? updated : t);
        if (selectedTask?.id === updated.id) {
          selectedTask = updated;
        }
      } else if (event.type === 'comment_added') {
        if (selectedTask?.id === event.data.task_id) {
        }
      }
    }, (connected) => {
      sseConnected = connected;
    });
  }

  function handleSort(field: string) {
    const criteria = sortStr ? parseSortCriteria(sortStr) : [];
    const existing = criteria.findIndex(c => c.field === field);

    if (existing === 0) {
      criteria[0].dir = criteria[0].dir === 'asc' ? 'desc' : 'asc';
    } else if (existing > 0) {
      const [removed] = criteria.splice(existing, 1);
      criteria.unshift(removed);
    } else {
      criteria.unshift({ field, dir: 'asc' });
    }

    const reverseFieldMap: Record<string, string> = {
      id: 'ID', title: 'TITLE', status: 'STATUS', importance: 'IMPORTANCE',
      estimated_effort: 'EFFORT', created_time: 'CREATED',
      assignee_name: 'ASSIGNEE', last_activity_time: 'LAST_ACTIVITY',
    };
    sortStr = criteria.map(c => `${reverseFieldMap[c.field] || c.field.toUpperCase()} ${c.dir}`).join(', ');
    sortField = criteria[0]?.field || 'id';
    sortDir = criteria[0]?.dir || 'asc';
    writeURL();
  }

  function parseSortCriteria(s: string): { field: string; dir: 'asc' | 'desc' }[] {
    if (!s.trim()) return [];
    return s.split(',').map(part => {
      const tokens = part.trim().split(/\s+/);
      const field = (tokens[0] || '').toLowerCase();
      const dir = (tokens[1] || 'asc').toLowerCase() === 'desc' ? 'desc' as const : 'asc' as const;
      const fieldMap: Record<string, string> = {
        id: 'id', title: 'title', status: 'status', importance: 'importance',
        estimated_effort: 'estimated_effort', effort: 'estimated_effort',
        created_time: 'created_time', created: 'created_time',
        assignee: 'assignee_name', assignee_name: 'assignee_name',
        last_activity: 'last_activity_time', last_activity_time: 'last_activity_time',
      };
      return { field: fieldMap[field] || field, dir };
    }).filter(c => c.field);
  }

  let sortedTasks = $derived.by(() => {
    const criteria = sortStr ? parseSortCriteria(sortStr) : [{ field: sortField, dir: sortDir }];
    const sorted = [...tasks].sort((a, b) => {
      for (const { field, dir } of criteria) {
        const key = field as keyof Task;
        let av = a[key] ?? '';
        let bv = b[key] ?? '';
        if (typeof av === 'number' && typeof bv === 'number') {
          if (av !== bv) return dir === 'asc' ? av - bv : bv - av;
        } else {
          const as = String(av).toLowerCase();
          const bs = String(bv).toLowerCase();
          if (as < bs) return dir === 'asc' ? -1 : 1;
          if (as > bs) return dir === 'asc' ? 1 : -1;
        }
      }
      return 0;
    });
    return sorted;
  });

  async function loadBoards() {
    boardsLoading = true;
    try {
      boards = await listBoards(showArchivedBoards);
      if (boards.length > 0 && !selectedBoard) {
        const fromUrl = urlBoardId != null ? boards.find(b => b.id === urlBoardId) : null;
        selectedBoard = fromUrl ?? boards.find(b => !b.archived) ?? boards[0];
        urlBoardId = null;
      }
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load boards';
    } finally {
      boardsLoading = false;
    }
  }

  async function handleArchiveBoard(board: Board) {
    const updated = await editBoard(board.id, { archived: !board.archived });
    boards = boards.map(b => b.id === updated.id ? updated : b);
    if (updated.archived && selectedBoard?.id === updated.id) {
      selectedBoard = boards.find(b => !b.archived) ?? null;
      loadTasks();
    }
  }

  function focusOnMount(node: HTMLElement) {
    node.focus();
  }

  function startEditBoardName() {
    if (!selectedBoard) return;
    editBoardNameValue = selectedBoard.name;
    editingBoardName = true;
  }

  async function saveBoardName() {
    if (!selectedBoard) return;
    const name = editBoardNameValue.trim();
    if (name && name !== selectedBoard.name) {
      const updated = await editBoard(selectedBoard.id, { name });
      boards = boards.map(b => b.id === updated.id ? updated : b);
      selectedBoard = updated;
    }
    editingBoardName = false;
  }

  function cancelEditBoardName() {
    editingBoardName = false;
  }

  function toggleArchivedBoards() {
    showArchivedBoards = !showArchivedBoards;
    loadBoards();
  }

  async function loadTasks() {
    if (!selectedBoard) {
      tasks = [];
      loading = false;
      return;
    }
    loading = true;
    error = '';
    try {
      tasks = await listTasks(selectedBoard.id, filterStr || undefined);
      try {
        const ids = await getUnreadTaskIds(selectedBoard.id);
        unreadTaskIds = new Set(ids);
      } catch { unreadTaskIds = new Set(); }
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load tasks';
    } finally {
      loading = false;
    }
  }

  function handleBoardSelect(board: Board) {
    selectedBoard = board;
    selectedTask = null;
    showUsers = false;
    loadTasks();
    setupSSE(board.id);
    writeURL();
  }

  function handleBoardCreated(board: Board) {
    boards = [...boards, board];
  }

  async function handleBatchMarkRead(taskIds: number[]) {
    if (!selectedBoard) return;
    try {
      await markTasksRead(selectedBoard.id, taskIds);
      const next = new Set(unreadTaskIds);
      for (const id of taskIds) next.delete(id);
      unreadTaskIds = next;
    } catch {}
  }

  function handleSelect(task: Task) {
    selectedTask = task;
    // Mark as read (remove from unread set)
    if (unreadTaskIds.has(task.id)) {
      const next = new Set(unreadTaskIds);
      next.delete(task.id);
      unreadTaskIds = next;
    }
  }

  // TODO: server requires status_reason from non-admin users when transitioning to
  // DONE / WAITING_FOR_COMMAND_EXECUTION / CANCELLED (NOT_REPRODUCIBLE is no_drag).
  // Kanban drag currently sends no reason — the optimistic update will roll back
  // on a 422 from the server. Add a reason prompt here when surfacing the error
  // becomes a UX issue. (TaskDetail.svelte's edit form already collects one.)
  async function handleKanbanStatusChange(task: Task, newStatus: string) {
    const oldStatus = task.status;
    tasks = tasks.map(t => t.id === task.id ? { ...t, status: newStatus as Task['status'] } : t);
    try {
      const updated = await editTask(selectedBoard!.id, task.id, { status: newStatus as Task['status'] });
      tasks = tasks.map(t => t.id === updated.id ? updated : t);
    } catch (e) {
      tasks = tasks.map(t => t.id === task.id ? { ...t, status: oldStatus } : t);
    }
  }

  function handleTaskUpdated(updated: Task) {
    tasks = tasks.map(t => t.id === updated.id ? updated : t);
    selectedTask = updated;
  }

  function handleTaskCreated(task: Task) {
    if (!tasks.find(t => t.id === task.id)) {
      tasks = [task, ...tasks];
    }
    showForm = false;
  }

  function handleFilter(f: string) {
    filterStr = f;
    writeURL();
    loadTasks();
  }

  function handleSortStr(s: string) {
    sortStr = s;
    const criteria = parseSortCriteria(s);
    sortField = criteria[0]?.field || 'id';
    sortDir = criteria[0]?.dir || 'asc';
    writeURL();
  }

  import { STATUSES, STATUS_LABELS } from './lib/statuses';

  const KANBAN_STATUS_ORDER = [...STATUSES];

  function loadVisibleStatuses(): Set<string> {
    try {
      const saved = localStorage.getItem('kanbanVisibleStatuses');
      if (saved) return new Set(JSON.parse(saved));
    } catch {}
    return new Set(['NEW', 'STARTED', 'BLOCKED', 'WAITING_FOR_COMMAND_EXECUTION']);
  }

  let kanbanVisibleStatuses = $state(loadVisibleStatuses());
  let showColumnConfig = $state(false);

  function loadKanbanOrder(): string[] {
    try {
      const saved = localStorage.getItem('kanbanStatusOrder');
      if (saved) return JSON.parse(saved);
    } catch {}
    return [...KANBAN_STATUS_ORDER];
  }
  let kanbanStatusOrder = $state<string[]>(loadKanbanOrder());
  function saveKanbanOrder() {
    localStorage.setItem('kanbanStatusOrder', JSON.stringify(kanbanStatusOrder));
  }

  let dragIndex = $state<number | null>(null);

  function handleDragStart(index: number) {
    dragIndex = index;
  }
  function handleDragOver(e: DragEvent, index: number) {
    e.preventDefault();
    if (dragIndex === null || dragIndex === index) return;
    const newOrder = [...kanbanStatusOrder];
    const [moved] = newOrder.splice(dragIndex, 1);
    newOrder.splice(index, 0, moved);
    kanbanStatusOrder = newOrder;
    dragIndex = index;
  }
  function handleDragEnd() {
    dragIndex = null;
    saveKanbanOrder();
  }

  function statusCssVar(status: string): string {
    const map: Record<string, string> = {
      'WAITING_FOR_COMMAND_EXECUTION': 'waiting',
      'NOT_REPRODUCIBLE': 'not-reproducible',
    };
    return map[status] ?? status.toLowerCase();
  }

  function handleColumnsClickOutside(e: MouseEvent) {
    const dropdown = (e.target as HTMLElement).closest('.columns-dropdown');
    if (!dropdown && showColumnConfig) {
      showColumnConfig = false;
    }
  }
  $effect(() => {
    document.addEventListener('mousedown', handleColumnsClickOutside);
    return () => document.removeEventListener('mousedown', handleColumnsClickOutside);
  });

  function toggleKanbanStatus(status: string) {
    const next = new Set(kanbanVisibleStatuses);
    if (next.has(status)) next.delete(status);
    else next.add(status);
    kanbanVisibleStatuses = next;
    localStorage.setItem('kanbanVisibleStatuses', JSON.stringify([...next]));
  }

  function showAllKanbanStatuses() {
    kanbanVisibleStatuses = new Set(KANBAN_STATUS_ORDER);
    localStorage.setItem('kanbanVisibleStatuses', JSON.stringify([...KANBAN_STATUS_ORDER]));
  }

</script>

{#if !authChecked}
  <div class="flex items-center justify-center min-h-screen bg-bg">
    <p class="text-text-secondary animate-spin">Loading...</p>
  </div>
{:else if !currentUser}
  <div class="flex items-center justify-center min-h-screen bg-bg">
    <div class="bg-surface border border-border rounded-lg p-8 w-full max-w-sm shadow-lg">
      <h1 class="text-xl font-bold mb-1 text-text">TaskPlanner</h1>
      <p class="text-sm text-text-secondary mb-6">Enter your access token to continue.</p>
      <div class="flex flex-col gap-3">
        <input
          type="password"
          bind:value={loginToken}
          placeholder="tp_..."
          class="text-sm"
          onkeydown={(e) => { if (e.key === 'Enter') handleLogin(); }}
        />
        {#if loginError}
          <p class="text-xs text-[color:var(--importance-high)] m-0">{loginError}</p>
        {/if}
        <button
          class="bg-primary text-white font-semibold py-2 hover:bg-primary-hover disabled:opacity-50"
          onclick={handleLogin}
          disabled={loginLoading}
        >
          {loginLoading ? 'Verifying...' : 'Login'}
        </button>
      </div>
      <div class="mt-4">
        <ThemeToggle />
      </div>
    </div>
  </div>
{:else}
<div class="flex min-h-screen">
  <BoardSidebar
    {boards}
    selected={selectedBoard}
    collapsed={sidebarCollapsed}
    showArchived={showArchivedBoards}
    onselect={handleBoardSelect}
    onboardcreated={handleBoardCreated}
    ontoggle={() => sidebarCollapsed = !sidebarCollapsed}
    onusers={() => showUsers = true}
    onarchive={handleArchiveBoard}
    ontogglearchived={toggleArchivedBoards}
  />

  <div class="flex-1 min-w-0 flex flex-col">
    <header class="flex flex-wrap md:flex-nowrap justify-between items-center px-2 md:px-4 py-1 border-b border-border sticky top-0 z-50 bg-surface gap-1">
      <div class="hidden md:flex items-center gap-3">
        <h1 class="text-base font-semibold ml-10">
          {#if selectedBoard && editingBoardName}
            <input
              class="text-base font-semibold bg-bg text-text border border-primary rounded px-1.5 py-0.5 w-[200px]"
              type="text"
              bind:value={editBoardNameValue}
              onkeydown={(e) => { if (e.key === 'Enter') saveBoardName(); if (e.key === 'Escape') cancelEditBoardName(); }}
              onblur={saveBoardName}
              use:focusOnMount
            />
          {:else if selectedBoard}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <span class="cursor-default select-none" ondblclick={startEditBoardName}>{selectedBoard.name}</span>
          {:else}
            TaskPlanner
          {/if}
        </h1>
      </div>
      {#if selectedBoard && !showUsers && !loading && !boardsLoading}
        <div class="flex-1 min-w-0 px-0 md:px-4 order-3 md:order-none w-full md:w-auto header-toolbar">
          <FilterBar onfilter={handleFilter} onsort={handleSortStr} initial={filterStr} initialSort={sortStr} />
        </div>
      {/if}
      <div class="flex items-center gap-1 md:gap-2 shrink-0 flex-wrap w-full md:w-auto justify-start">
        {#if view === 'card'}
          <div class="columns-dropdown relative">
            <button class="bg-bg text-text-secondary text-xs py-1 px-3 border border-border rounded cursor-pointer hover:text-text" onclick={() => showColumnConfig = !showColumnConfig}>
              Columns {showColumnConfig ? '\u25B2' : '\u25BC'}
            </button>
            {#if showColumnConfig}
              <div class="absolute top-full right-0 z-10 bg-surface border border-border rounded-md py-2 px-3 flex flex-col gap-1.5 min-w-[180px] shadow-[0_4px_12px_rgba(0,0,0,0.2)]">
                {#each kanbanStatusOrder as status, i}
                  <label class="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer" draggable="true"
                    ondragstart={() => handleDragStart(i)}
                    ondragover={(e) => handleDragOver(e, i)}
                    ondragend={handleDragEnd}>
                    <span class="cursor-grab opacity-40 text-sm leading-none select-none hover:opacity-80">&#x2807;</span>
                    <input type="checkbox" checked={kanbanVisibleStatuses.has(status)} onchange={() => toggleKanbanStatus(status)} />
                    <span class="w-2 h-2 rounded-full shrink-0" style="background: var(--status-{statusCssVar(status)})"></span>
                    {STATUS_LABELS[status as keyof typeof STATUS_LABELS]}
                  </label>
                {/each}
                <button class="bg-none border-none text-primary text-xs py-1 px-0 cursor-pointer text-left" onclick={showAllKanbanStatuses}>Show all</button>
              </div>
            {/if}
          </div>
        {/if}
        <button class="live-toggle flex items-center gap-1.5 bg-none p-1 border-none cursor-pointer {autoUpdate ? 'on' : ''}" onclick={toggleAutoUpdate} title={autoUpdate ? 'Auto-update ON' : 'Auto-update OFF'}>
          <span class="live-track w-[34px] h-[18px] rounded-[9px] bg-border flex items-center p-0.5 transition-colors duration-200"><span class="w-3.5 h-3.5 rounded-full bg-white transition-transform duration-200 live-knob"></span></span>
          <span class="text-xs text-text-secondary select-none live-label {autoUpdate && !sseConnected ? 'disconnected' : ''}">{autoUpdate ? (sseConnected ? 'Live' : 'Disconnected') : 'Paused'}</span>
        </button>
        <UserIdentity selected={currentUser} onchange={(u) => { if (!u) handleLogout(); else currentUser = u; }} />
        <ThemeToggle />
        <ViewToggle {view} onchange={(v) => { view = v; writeURL(); }} />
        {#if selectedBoard}
          <button class="bg-primary text-white font-semibold py-1 px-4 text-sm hover:bg-primary-hover" onclick={() => showForm = true}>+ New Task</button>
        {/if}
      </div>
    </header>

    <main class="flex-1 dark-main">
      {#if showUsers}
        <UsersPage onclose={() => showUsers = false} />
      {:else if boardsLoading}
        <p class="text-center py-10 text-text-secondary flex items-center justify-center gap-2.5"><span class="inline-block w-[18px] h-[18px] border-[2.5px] border-border border-t-primary rounded-full animate-spin"></span> Loading boards...</p>
      {:else if boards.length === 0}
        <div class="text-center py-10 text-text-secondary">
          <p>No boards yet. Create your first board to get started.</p>
        </div>
      {:else if !selectedBoard}
        <p class="text-center py-10 text-text-secondary">Select a board to view tasks.</p>
      {:else if loading}
        <p class="text-center py-10 text-text-secondary flex items-center justify-center gap-2.5"><span class="inline-block w-[18px] h-[18px] border-[2.5px] border-border border-t-primary rounded-full animate-spin"></span> Loading tasks...</p>
      {:else if error}
        <p class="text-center py-10 text-[color:var(--importance-high)]">{error}</p>
        <button class="block mx-auto bg-bg text-text" onclick={loadTasks}>Retry</button>
      {:else}
        {#if view === 'list'}
          <TaskList tasks={sortedTasks} onselect={handleSelect} {sortField} {sortDir} onsort={handleSort} {unreadTaskIds} onbatchmarkread={handleBatchMarkRead} />
        {:else}
          <TaskGrid tasks={sortedTasks} onselect={handleSelect} onstatuschange={handleKanbanStatusChange} visibleStatuses={kanbanVisibleStatuses} statusOrder={kanbanStatusOrder} {unreadTaskIds} />
        {/if}
      {/if}
    </main>
  </div>
</div>

{#if selectedTask && selectedBoard}
  <TaskDetail
    task={selectedTask}
    boardId={selectedBoard.id}
    currentUserId={currentUser?.id ?? null}
    onclose={() => selectedTask = null}
    onupdated={handleTaskUpdated}
  />
{/if}

{#if showForm && selectedBoard}
  <TaskForm
    boardId={selectedBoard.id}
    currentUserId={currentUser?.id ?? null}
    oncreated={handleTaskCreated}
    oncancel={() => showForm = false}
  />
{/if}
{/if}

<style>
  :global([data-theme="dark"]) .dark-main {
    background: #101010;
  }
  .header-toolbar :global(.bar) {
    margin-bottom: 0;
    padding: 0;
  }
  .live-toggle.on .live-track {
    background: var(--status-new);
  }
  .live-toggle.on .live-knob {
    transform: translateX(16px);
  }
  .live-toggle.on .live-label {
    color: var(--status-new);
  }
  .live-toggle.on .live-label.disconnected {
    color: #e74c3c;
  }
</style>

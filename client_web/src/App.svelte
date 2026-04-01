<script lang="ts">
  import { listTasks, listBoards, editBoard, subscribeToBoardEvents, type Task, type Board, type BoardEvent } from './lib/api';
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

  // Restore current user from localStorage
  async function restoreCurrentUser() {
    const savedId = localStorage.getItem('currentUserId');
    if (savedId) {
      try {
        const users = await listUsers();
        currentUser = users.find(u => u.id === Number(savedId)) || null;
      } catch {}
    }
  }
  restoreCurrentUser();
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
        // Only add if not already in list (avoid duplicates from own actions)
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
        // Refresh task detail if open for this task
        if (selectedTask?.id === event.data.task_id) {
          // CommentSection will handle its own refresh via the event
        }
      }
    }, (connected) => {
      sseConnected = connected;
    });
  }

  function handleSort(field: string) {
    // Parse current sort criteria
    const criteria = sortStr ? parseSortCriteria(sortStr) : [];
    const existing = criteria.findIndex(c => c.field === field);

    if (existing === 0) {
      // Already top priority — toggle direction
      criteria[0].dir = criteria[0].dir === 'asc' ? 'desc' : 'asc';
    } else if (existing > 0) {
      // Already in list — move to top priority
      const [removed] = criteria.splice(existing, 1);
      criteria.unshift(removed);
    } else {
      // New — add as top priority
      criteria.unshift({ field, dir: 'asc' });
    }

    // Rebuild sort string with uppercase field names
    const reverseFieldMap: Record<string, string> = {
      id: 'ID', title: 'TITLE', status: 'STATUS', importance: 'IMPORTANCE',
      estimated_effort: 'EFFORT', created_time: 'CREATED',
      assignee_name: 'ASSIGNEE',
    };
    sortStr = criteria.map(c => `${reverseFieldMap[c.field] || c.field.toUpperCase()} ${c.dir}`).join(', ');
    // Also update legacy sort fields for column header indicators
    sortField = criteria[0]?.field || 'id';
    sortDir = criteria[0]?.dir || 'asc';
    writeURL();
  }

  // Parse sort string like "IMPORTANCE desc, CREATED_TIME asc"
  function parseSortCriteria(s: string): { field: string; dir: 'asc' | 'desc' }[] {
    if (!s.trim()) return [];
    return s.split(',').map(part => {
      const tokens = part.trim().split(/\s+/);
      const field = (tokens[0] || '').toLowerCase();
      const dir = (tokens[1] || 'asc').toLowerCase() === 'desc' ? 'desc' as const : 'asc' as const;
      // Map uppercase field names to task keys
      const fieldMap: Record<string, string> = {
        id: 'id', title: 'title', status: 'status', importance: 'importance',
        estimated_effort: 'estimated_effort', effort: 'estimated_effort',
        created_time: 'created_time', created: 'created_time',
        assignee: 'assignee_name', assignee_name: 'assignee_name',
      };
      return { field: fieldMap[field] || field, dir };
    }).filter(c => c.field);
  }

  // Client-side sort (filtering is server-side)
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

  function handleSelect(task: Task) {
    selectedTask = task;
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
    // Sync column header indicators with first sort criterion
    const criteria = parseSortCriteria(s);
    sortField = criteria[0]?.field || 'id';
    sortDir = criteria[0]?.dir || 'asc';
    writeURL();
  }

  import { STATUSES, STATUS_LABELS } from './lib/statuses';

  // Kanban column visibility (moved from TaskGrid to header)
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

  // Kanban column order (drag-rearrangeable)
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

  // Status CSS var mapping (same as TaskGrid)
  function statusCssVar(status: string): string {
    const map: Record<string, string> = {
      'WAITING_FOR_COMMAND_EXECUTION': 'waiting',
      'NOT_REPRODUCIBLE': 'not-reproducible',
    };
    return map[status] ?? status.toLowerCase();
  }

  // Click-outside handler for columns dropdown
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

  loadBoards().then(() => {
    loadTasks();
    if (selectedBoard) setupSSE(selectedBoard.id);
  });
</script>

<div class="layout">
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

  <div class="main">
    <header>
      <div class="header-left">
        <h1>
          {#if selectedBoard && editingBoardName}
            <input
              class="board-name-input"
              type="text"
              bind:value={editBoardNameValue}
              onkeydown={(e) => { if (e.key === 'Enter') saveBoardName(); if (e.key === 'Escape') cancelEditBoardName(); }}
              onblur={saveBoardName}
              autofocus
            />
          {:else if selectedBoard}
            <span class="board-name-text" ondblclick={startEditBoardName}>{selectedBoard.name}</span>
          {:else}
            TaskPlanner
          {/if}
        </h1>
      </div>
      {#if selectedBoard && !showUsers && !loading && !boardsLoading}
        <div class="header-toolbar">
          <FilterBar onfilter={handleFilter} onsort={handleSortStr} initial={filterStr} initialSort={sortStr} />
        </div>
      {/if}
      <div class="header-actions">
        {#if view === 'card'}
          <div class="columns-dropdown">
            <button class="columns-btn" onclick={() => showColumnConfig = !showColumnConfig}>
              Columns {showColumnConfig ? '▲' : '▼'}
            </button>
            {#if showColumnConfig}
              <div class="columns-picker">
                {#each kanbanStatusOrder as status, i}
                  <label class="col-check" draggable="true"
                    ondragstart={() => handleDragStart(i)}
                    ondragover={(e) => handleDragOver(e, i)}
                    ondragend={handleDragEnd}>
                    <span class="drag-handle">⠿</span>
                    <input type="checkbox" checked={kanbanVisibleStatuses.has(status)} onchange={() => toggleKanbanStatus(status)} />
                    <span class="col-check-dot" style="background: var(--status-{statusCssVar(status)})"></span>
                    {STATUS_LABELS[status as keyof typeof STATUS_LABELS]}
                  </label>
                {/each}
                <button class="show-all-btn" onclick={showAllKanbanStatuses}>Show all</button>
              </div>
            {/if}
          </div>
        {/if}
        <button class="live-toggle" class:on={autoUpdate} onclick={toggleAutoUpdate} title={autoUpdate ? 'Auto-update ON' : 'Auto-update OFF'}>
          <span class="live-track"><span class="live-knob"></span></span>
          <span class="live-label" class:disconnected={autoUpdate && !sseConnected}>{autoUpdate ? (sseConnected ? 'Live' : 'Disconnected') : 'Paused'}</span>
        </button>
        <UserIdentity selected={currentUser} onchange={(u) => currentUser = u} />
        <ThemeToggle />
        <ViewToggle {view} onchange={(v) => { view = v; writeURL(); }} />
        {#if selectedBoard}
          <button class="new-task-btn" onclick={() => showForm = true}>+ New Task</button>
        {/if}
      </div>
    </header>

    <main>
      {#if showUsers}
        <UsersPage onclose={() => showUsers = false} />
      {:else if boardsLoading}
        <p class="center loading-indicator"><span class="spinner"></span> Loading boards...</p>
      {:else if boards.length === 0}
        <div class="center">
          <p>No boards yet. Create your first board to get started.</p>
        </div>
      {:else if !selectedBoard}
        <p class="center">Select a board to view tasks.</p>
      {:else if loading}
        <p class="center loading-indicator"><span class="spinner"></span> Loading tasks...</p>
      {:else if error}
        <p class="center error">{error}</p>
        <button class="retry" onclick={loadTasks}>Retry</button>
      {:else}
        {#if view === 'list'}
          <TaskList tasks={sortedTasks} onselect={handleSelect} {sortField} {sortDir} onsort={handleSort} />
        {:else}
          <TaskGrid tasks={sortedTasks} onselect={handleSelect} visibleStatuses={kanbanVisibleStatuses} statusOrder={kanbanStatusOrder} />
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
    currentUsername={currentUser?.username ?? null}
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

<style>
  .layout {
    display: flex;
    min-height: 100vh;
  }
  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 16px;
    border-bottom: 1px solid var(--color-border);
    position: sticky;
    top: 0;
    z-index: 50;
    background: var(--color-surface);
  }
  h1 {
    font-size: 16px;
    font-weight: 600;
    margin-left: 40px;
  }
  .board-name-text {
    cursor: default;
    user-select: none;
  }
  .board-name-input {
    font-size: 16px;
    font-weight: 600;
    background: var(--color-bg);
    color: var(--color-text);
    border: 1px solid var(--color-primary);
    border-radius: 4px;
    padding: 2px 6px;
    width: 200px;
  }
  .header-toolbar {
    flex: 1;
    min-width: 0;
    padding: 0 16px;
  }
  .header-toolbar :global(.bar) {
    margin-bottom: 0;
    padding: 0;
  }
  .header-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }
  .live-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    background: none;
    padding: 4px;
    border: none;
    cursor: pointer;
  }
  .live-track {
    width: 34px;
    height: 18px;
    border-radius: 9px;
    background: var(--color-border);
    display: flex;
    align-items: center;
    padding: 2px;
    transition: background 0.2s;
  }
  .live-toggle.on .live-track {
    background: var(--status-new);
  }
  .live-knob {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: white;
    transition: transform 0.2s;
  }
  .live-toggle.on .live-knob {
    transform: translateX(16px);
  }
  .live-label {
    font-size: 12px;
    color: var(--color-text-secondary);
    user-select: none;
  }
  .live-toggle.on .live-label {
    color: var(--status-new);
  }
  .live-toggle.on .live-label.disconnected {
    color: #e74c3c;
  }
  .columns-dropdown {
    position: relative;
  }
  .columns-btn {
    background: var(--color-bg);
    color: var(--color-text-secondary);
    font-size: 12px;
    padding: 4px 12px;
    border: 1px solid var(--color-border);
    border-radius: 4px;
    cursor: pointer;
  }
  .columns-btn:hover {
    color: var(--color-text);
  }
  .columns-picker {
    position: absolute;
    top: 100%;
    right: 0;
    z-index: 10;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    padding: 8px 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 180px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  }
  .col-check {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--color-text-secondary);
    cursor: pointer;
  }
  .col-check-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .drag-handle {
    cursor: grab;
    opacity: 0.4;
    font-size: 14px;
    line-height: 1;
    user-select: none;
  }
  .drag-handle:hover {
    opacity: 0.8;
  }
  .columns-picker .show-all-btn {
    background: none;
    border: none;
    color: var(--color-primary);
    font-size: 12px;
    padding: 4px 0;
    cursor: pointer;
    text-align: left;
  }
  .new-task-btn {
    background: var(--color-primary);
    color: white;
    font-weight: 600;
    padding: 8px 20px;
  }
  .new-task-btn:hover {
    background: var(--color-primary-hover);
  }
  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  main {
    flex: 1;
    padding: 0;
  }
  :global([data-theme="dark"]) main {
    background: #101010;
  }
  .center {
    text-align: center;
    padding: 40px;
    color: var(--color-text-secondary);
  }
  .error {
    color: var(--importance-high);
  }
  .retry {
    display: block;
    margin: 0 auto;
    background: var(--color-bg);
    color: var(--color-text);
  }
  .loading-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
  }
  .spinner {
    display: inline-block;
    width: 18px;
    height: 18px;
    border: 2.5px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  @media (max-width: 768px) {
    header {
      flex-wrap: wrap;
      padding: 6px 8px;
      gap: 4px;
    }
    .header-left {
      display: none;
    }
    .header-toolbar {
      order: 3;
      width: 100%;
      padding: 0;
    }
    .header-actions {
      gap: 4px;
      flex-wrap: wrap;
      width: 100%;
      justify-content: flex-start;
    }
    main {
      padding: 0;
    }
  }
</style>

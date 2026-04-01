<script lang="ts">
  import { createBoard, editBoard, type Board } from '../lib/api';

  interface Props {
    boards: Board[];
    selected: Board | null;
    collapsed: boolean;
    showArchived: boolean;
    onselect: (board: Board) => void;
    onboardcreated: (board: Board) => void;
    ontoggle: () => void;
    onusers: () => void;
    onarchive: (board: Board) => void;
    ontogglearchived: () => void;
  }

  let { boards, selected, collapsed, showArchived, onselect, onboardcreated, ontoggle, onusers, onarchive, ontogglearchived }: Props = $props();

  let creating = $state(false);
  let newName = $state('');
  let submitting = $state(false);
  let error = $state('');
  let sidebarWidth = $state(parseInt(localStorage.getItem('sidebarWidth') || '220'));
  let resizing = $state(false);

  function startResize(e: MouseEvent) {
    e.preventDefault();
    resizing = true;
    document.body.classList.add('select-none');
    const onMove = (ev: MouseEvent) => {
      const w = Math.max(150, Math.min(500, ev.clientX));
      sidebarWidth = w;
    };
    const onUp = () => {
      resizing = false;
      document.body.classList.remove('select-none');
      localStorage.setItem('sidebarWidth', String(sidebarWidth));
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  function selectBoard(board: Board) {
    onselect(board);
  }

  async function handleCreate() {
    const name = newName.trim();
    if (!name) {
      error = 'Name is required';
      return;
    }
    error = '';
    submitting = true;
    try {
      const board = await createBoard({ name });
      onboardcreated(board);
      onselect(board);
      newName = '';
      creating = false;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to create board';
    } finally {
      submitting = false;
    }
  }
</script>

<aside class="sidebar sticky top-0 h-screen flex shrink-0 z-[51] {collapsed ? 'collapsed' : ''}">
  <button class="tab absolute top-0 z-[51] w-8 h-10 bg-surface border border-border border-l-0 rounded-r-md text-text-secondary flex items-center justify-center cursor-pointer p-0 hover:bg-bg hover:text-text {collapsed ? 'left-0 rounded-r-md' : 'right-[-32px]'}" onclick={ontoggle} title={collapsed ? 'Show boards' : 'Hide boards'}>
    <svg width="8" height="14" viewBox="0 0 8 14" fill="none">
      {#if collapsed}
        <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      {:else}
        <path d="M7 1L1 7L7 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      {/if}
    </svg>
  </button>

  <div class="sidebar-inner bg-surface flex flex-col overflow-hidden relative {collapsed ? '' : 'border-r border-border'} {resizing ? '' : 'transition-[width] duration-200'}" style="width: {collapsed ? 0 : sidebarWidth}px">
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="resize-handle absolute top-0 right-0 w-1 h-full cursor-col-resize z-10 hover:bg-primary/30 {resizing ? 'bg-primary/30' : ''}" onmousedown={startResize}></div>
    <div class="px-3 pt-4 pb-3 border-b border-border flex items-center justify-between">
      <span class="text-[13px] font-bold uppercase tracking-wide text-text-secondary">Boards</span>
      {#if !creating}
        <button class="bg-none border-none text-text-secondary text-lg p-0 px-1 cursor-pointer leading-none hover:text-primary" onclick={() => creating = true} title="New board">+</button>
      {/if}
    </div>

  {#if creating}
    <div class="px-3 py-2.5 border-t border-border flex flex-col gap-1.5">
      <input
        type="text"
        bind:value={newName}
        placeholder="Board name"
        class="text-[13px] py-1.5 px-2"
        onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleCreate(); } if (e.key === 'Escape') { creating = false; newName = ''; error = ''; } }}
      />
      {#if error}
        <p class="text-[color:var(--importance-high)] text-xs m-0">{error}</p>
      {/if}
      <div class="flex gap-1.5 justify-end">
        <button class="bg-bg text-text py-1 px-2.5 text-xs" onclick={() => { creating = false; newName = ''; error = ''; }}>Cancel</button>
        <button class="bg-primary text-white py-1 px-2.5 text-xs disabled:opacity-50 disabled:cursor-default" onclick={handleCreate} disabled={submitting}>
          {submitting ? '...' : 'Create'}
        </button>
      </div>
    </div>
  {/if}

  <nav class="flex-1 overflow-y-auto py-2">
    {#each boards.filter(b => !b.archived) as board (board.id)}
      <div class="board-row flex items-center transition-[background] duration-100 hover:bg-bg {selected?.id === board.id ? 'active border-l-[3px] border-l-primary bg-bg' : ''}">
        <button
          class="flex items-center gap-2 flex-1 min-w-0 text-left py-2 pr-1 bg-none border-none rounded-none text-text cursor-pointer text-sm {selected?.id === board.id ? 'font-semibold pl-[9px]' : 'pl-3'}"
          onclick={() => selectBoard(board)}
          title={board.description || board.name}
        >
          <span class="text-primary text-[10px] shrink-0">&block;</span>
          <span class="overflow-hidden text-ellipsis whitespace-nowrap">{board.name}</span>
        </button>
        <button
          class="archive-btn bg-none border-none text-text-secondary cursor-pointer py-1 px-2 text-xs opacity-0 transition-opacity duration-100 shrink-0 hover:text-text"
          onclick={() => onarchive(board)}
          title="Archive board"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="3" width="20" height="5" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>
          </svg>
        </button>
      </div>
    {/each}

    {#if showArchived}
      {#each boards.filter(b => b.archived) as board (board.id)}
        <div class="board-row flex items-center transition-[background] duration-100 opacity-60 hover:bg-bg {selected?.id === board.id ? 'active border-l-[3px] border-l-primary bg-bg' : ''}">
          <button
            class="flex items-center gap-2 flex-1 min-w-0 text-left py-2 pr-1 bg-none border-none rounded-none text-text cursor-pointer text-sm {selected?.id === board.id ? 'font-semibold pl-[9px]' : 'pl-3'}"
            onclick={() => selectBoard(board)}
            title={board.description || board.name}
          >
            <span class="text-text-secondary text-[10px] shrink-0">&block;</span>
            <span class="overflow-hidden text-ellipsis whitespace-nowrap">{board.name}</span>
          </button>
          <button
            class="archive-btn bg-none border-none text-text-secondary cursor-pointer py-1 px-2 text-xs opacity-0 transition-opacity duration-100 shrink-0 hover:text-text"
            onclick={() => onarchive(board)}
            title="Unarchive board"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="2" y="3" width="20" height="5" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/><path d="M12 9v6"/>
            </svg>
          </button>
        </div>
      {/each}
    {/if}
  </nav>

  <div class="sidebar-footer border-t border-border py-2">
    <button class="block w-full text-left py-2 px-3 bg-none border-none rounded-none text-text-secondary cursor-pointer text-[13px] hover:bg-bg hover:text-text" onclick={ontogglearchived}>
      {showArchived ? 'Hide archived' : 'Archived boards'}
    </button>
    <button class="block w-full text-left py-2 px-3 bg-none border-none rounded-none text-text-secondary cursor-pointer text-[13px] hover:bg-bg hover:text-text" onclick={onusers}>Users</button>
  </div>
  </div>
</aside>

{#if !collapsed}
  <div class="sidebar-backdrop hidden" onclick={ontoggle} role="presentation"></div>
{/if}

<style>
  .board-row:hover .archive-btn {
    opacity: 1;
  }
  @media (max-width: 768px) {
    .sidebar-backdrop {
      display: block;
      position: fixed;
      inset: 0;
      z-index: 99;
      background: rgba(0, 0, 0, 0.5);
    }
    .sidebar {
      width: 0;
      min-width: 0;
    }
    .sidebar .sidebar-inner {
      display: none;
    }
    .sidebar:not(.collapsed) .sidebar-inner {
      display: flex;
      position: fixed;
      top: 0;
      left: 0;
      bottom: 0;
      width: 220px;
      z-index: 100;
      background: var(--color-surface);
      box-shadow: 2px 0 8px rgba(0,0,0,0.3);
    }
    .sidebar .sidebar-footer {
      display: none;
    }
    .sidebar:not(.collapsed) .sidebar-footer {
      display: block;
      position: fixed;
      bottom: 0;
      left: 0;
      width: 220px;
      z-index: 100;
      background: var(--color-surface);
    }
  }
</style>

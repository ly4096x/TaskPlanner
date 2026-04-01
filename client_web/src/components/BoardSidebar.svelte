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

<aside class="sidebar" class:collapsed>
  <button class="tab" class:tab-collapsed={collapsed} onclick={ontoggle} title={collapsed ? 'Show boards' : 'Hide boards'}>
    <svg width="8" height="14" viewBox="0 0 8 14" fill="none">
      {#if collapsed}
        <path d="M1 1L7 7L1 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      {:else}
        <path d="M7 1L1 7L7 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      {/if}
    </svg>
  </button>

  <div class="sidebar-inner">
    <div class="sidebar-header">
      <span class="sidebar-title">Boards</span>
      {#if !creating}
        <button class="add-board-btn" onclick={() => creating = true} title="New board">+</button>
      {/if}
    </div>

  {#if creating}
    <div class="create-form">
      <input
        type="text"
        bind:value={newName}
        placeholder="Board name"
        onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleCreate(); } if (e.key === 'Escape') { creating = false; newName = ''; error = ''; } }}
      />
      {#if error}
        <p class="error">{error}</p>
      {/if}
      <div class="create-actions">
        <button class="cancel-btn" onclick={() => { creating = false; newName = ''; error = ''; }}>Cancel</button>
        <button class="create-btn" onclick={handleCreate} disabled={submitting}>
          {submitting ? '...' : 'Create'}
        </button>
      </div>
    </div>
  {/if}

  <nav class="board-list">
    {#each boards.filter(b => !b.archived) as board (board.id)}
      <div class="board-row" class:active={selected?.id === board.id}>
        <button
          class="board-item"
          class:active={selected?.id === board.id}
          onclick={() => selectBoard(board)}
          title={board.description || board.name}
        >
          <span class="board-icon">■</span>
          <span class="board-name">{board.name}</span>
        </button>
        <button
          class="archive-btn"
          onclick={() => onarchive(board)}
          title="Archive board"
        >✕</button>
      </div>
    {/each}

    {#if showArchived}
      {#each boards.filter(b => b.archived) as board (board.id)}
        <div class="board-row archived" class:active={selected?.id === board.id}>
          <button
            class="board-item"
            class:active={selected?.id === board.id}
            onclick={() => selectBoard(board)}
            title={board.description || board.name}
          >
            <span class="board-icon archived-icon">■</span>
            <span class="board-name">{board.name}</span>
          </button>
          <button
            class="archive-btn"
            onclick={() => onarchive(board)}
            title="Unarchive board"
          >↩</button>
        </div>
      {/each}
    {/if}
  </nav>

  <div class="sidebar-footer">
    <button class="footer-btn" onclick={ontogglearchived}>
      {showArchived ? 'Hide archived' : 'Archived boards'}
    </button>
    <button class="footer-btn" onclick={onusers}>Users</button>
  </div>
  </div>
</aside>

{#if !collapsed}
  <div class="sidebar-backdrop" onclick={ontoggle} role="presentation"></div>
{/if}

<style>
  .sidebar {
    position: sticky;
    top: 0;
    height: 100vh;
    display: flex;
    flex-shrink: 0;
    z-index: 51;
  }
  .sidebar-inner {
    width: 220px;
    background: var(--color-surface);
    border-right: 1px solid var(--color-border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    transition: width 0.2s;
  }
  .sidebar.collapsed .sidebar-inner {
    width: 0;
    border-right: none;
  }
  .tab {
    position: absolute;
    top: 0px;
    right: -32px;
    z-index: 51;
    width: 32px;
    height: 40px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-left: none;
    border-radius: 0 6px 6px 0;
    color: var(--color-text-secondary);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    padding: 0;
  }
  .tab-collapsed {
    right: auto;
    left: 0;
    border-left: none;
    border-radius: 0 6px 6px 0;
  }
  .tab:hover {
    background: var(--color-bg);
    color: var(--color-text);
  }
  .sidebar-header {
    padding: 16px 12px 12px;
    border-bottom: 1px solid var(--color-border);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .add-board-btn {
    background: none;
    border: none;
    color: var(--color-text-secondary);
    font-size: 18px;
    padding: 0 4px;
    cursor: pointer;
    line-height: 1;
  }
  .add-board-btn:hover {
    color: var(--color-primary);
  }
  .sidebar-title {
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--color-text-secondary);
  }
  .board-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
  }
  .board-row {
    display: flex;
    align-items: center;
  }
  .board-row:hover .archive-btn {
    opacity: 1;
  }
  .board-row.active {
    border-left: 3px solid var(--color-primary);
  }
  .board-row.archived {
    opacity: 0.6;
  }
  .board-item {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
    text-align: left;
    padding: 8px 4px 8px 12px;
    background: none;
    border: none;
    border-radius: 0;
    color: var(--color-text);
    cursor: pointer;
    font-size: 14px;
    transition: background 0.1s;
  }
  .board-row:hover .board-item,
  .board-row.active .board-item {
    background: var(--color-bg);
  }
  .board-row.active .board-item {
    font-weight: 600;
    padding-left: 9px;
  }
  .archive-btn {
    background: none;
    border: none;
    color: var(--color-text-secondary);
    cursor: pointer;
    padding: 4px 8px;
    font-size: 12px;
    opacity: 0;
    transition: opacity 0.1s;
    flex-shrink: 0;
  }
  .archive-btn:hover {
    color: var(--color-text);
  }
  .archived-icon {
    color: var(--color-text-secondary) !important;
  }
  .board-icon {
    color: var(--color-primary);
    font-size: 10px;
    flex-shrink: 0;
  }
  .board-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sidebar-footer {
    border-top: 1px solid var(--color-border);
    padding: 8px 0;
  }
  .footer-btn {
    display: block;
    width: 100%;
    text-align: left;
    padding: 8px 12px;
    background: none;
    border: none;
    border-radius: 0;
    color: var(--color-text-secondary);
    cursor: pointer;
    font-size: 13px;
  }
  .footer-btn:hover {
    background: var(--color-bg);
    color: var(--color-text);
  }
  .create-form {
    padding: 10px 12px;
    border-top: 1px solid var(--color-border);
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .create-form input {
    font-size: 13px;
    padding: 6px 8px;
  }
  .error {
    color: var(--importance-high);
    font-size: 12px;
    margin: 0;
  }
  .create-actions {
    display: flex;
    gap: 6px;
    justify-content: flex-end;
  }
  .cancel-btn {
    background: var(--color-bg);
    color: var(--color-text);
    padding: 4px 10px;
    font-size: 12px;
  }
  .create-btn {
    background: var(--color-primary);
    color: white;
    padding: 4px 10px;
    font-size: 12px;
  }
  .create-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .sidebar-backdrop {
    display: none;
  }
  @media (max-width: 768px) {
    .sidebar-backdrop {
      display: block;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
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

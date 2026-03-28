<script lang="ts">
  import { createBoard, type Board } from '../lib/api';

  interface Props {
    boards: Board[];
    selected: Board | null;
    onselect: (board: Board) => void;
    onboardcreated: (board: Board) => void;
  }

  let { boards, selected, onselect, onboardcreated }: Props = $props();

  let open = $state(false);
  let creating = $state(false);
  let newName = $state('');
  let submitting = $state(false);
  let error = $state('');

  function toggle() {
    open = !open;
    if (!open) {
      creating = false;
      newName = '';
      error = '';
    }
  }

  function selectBoard(board: Board) {
    onselect(board);
    open = false;
    creating = false;
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
      open = false;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to create board';
    } finally {
      submitting = false;
    }
  }
</script>

<div class="board-selector">
  <button class="selector-btn" onclick={toggle}>
    {selected ? selected.name : 'Select board'}
    <span class="arrow">{open ? '\u25B2' : '\u25BC'}</span>
  </button>

  {#if open}
    <div class="dropdown">
      {#each boards as board (board.id)}
        <button
          class="board-item"
          class:active={selected?.id === board.id}
          onclick={() => selectBoard(board)}
        >
          {board.name}
        </button>
      {/each}

      {#if creating}
        <div class="create-form">
          <input
            type="text"
            bind:value={newName}
            placeholder="Board name"
            onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleCreate(); } }}
          />
          {#if error}
            <p class="error">{error}</p>
          {/if}
          <div class="create-actions">
            <button type="button" class="cancel-btn" onclick={() => { creating = false; newName = ''; error = ''; }}>Cancel</button>
            <button type="button" class="create-btn" onclick={handleCreate} disabled={submitting}>
              {submitting ? 'Creating...' : 'Create'}
            </button>
          </div>
        </div>
      {:else}
        <button class="new-board-btn" onclick={() => creating = true}>+ New Board</button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .board-selector {
    position: relative;
  }
  .selector-btn {
    background: var(--color-bg);
    color: var(--color-text);
    padding: 8px 16px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
  }
  .arrow {
    font-size: 10px;
    color: var(--color-text-secondary);
  }
  .dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    min-width: 200px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    box-shadow: 0 4px 16px rgba(0,0,0,0.15);
    z-index: 50;
    margin-top: 4px;
    overflow: hidden;
  }
  .board-item {
    display: block;
    width: 100%;
    text-align: left;
    padding: 10px 16px;
    background: none;
    border: none;
    border-radius: 0;
    color: var(--color-text);
    cursor: pointer;
    font-size: 14px;
  }
  .board-item:hover {
    background: var(--color-bg);
  }
  .board-item.active {
    background: var(--color-bg);
    font-weight: 600;
  }
  .new-board-btn {
    display: block;
    width: 100%;
    text-align: left;
    padding: 10px 16px;
    background: none;
    border: none;
    border-top: 1px solid var(--color-border);
    border-radius: 0;
    color: var(--color-primary);
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
  }
  .new-board-btn:hover {
    background: var(--color-bg);
  }
  .create-form {
    padding: 12px 16px;
    border-top: 1px solid var(--color-border);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .create-form input {
    font-size: 14px;
    padding: 6px 10px;
  }
  .error {
    color: var(--importance-high);
    font-size: 12px;
    margin: 0;
  }
  .create-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
  .cancel-btn {
    background: var(--color-bg);
    color: var(--color-text);
    padding: 4px 12px;
    font-size: 13px;
  }
  .create-btn {
    background: var(--color-primary);
    color: white;
    padding: 4px 12px;
    font-size: 13px;
  }
  .create-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>

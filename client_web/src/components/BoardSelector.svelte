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

<div class="relative">
  <button class="bg-bg text-text py-2 px-4 font-semibold flex items-center gap-2 cursor-pointer rounded-[--radius]" onclick={toggle}>
    {selected ? selected.name : 'Select board'}
    <span class="text-[10px] text-text-secondary">{open ? '\u25B2' : '\u25BC'}</span>
  </button>

  {#if open}
    <div class="absolute top-full left-0 min-w-[200px] bg-surface border border-border rounded-[--radius] shadow-[0_4px_16px_rgba(0,0,0,0.15)] z-50 mt-1 overflow-hidden">
      {#each boards as board (board.id)}
        <button
          class="block w-full text-left py-2.5 px-4 bg-none border-none rounded-none text-text cursor-pointer text-sm hover:bg-bg {selected?.id === board.id ? 'bg-bg font-semibold' : ''}"
          onclick={() => selectBoard(board)}
        >
          {board.name}
        </button>
      {/each}

      {#if creating}
        <div class="px-4 py-3 border-t border-border flex flex-col gap-2">
          <input
            type="text"
            bind:value={newName}
            placeholder="Board name"
            class="text-sm py-1.5 px-2.5"
            onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleCreate(); } }}
          />
          {#if error}
            <p class="text-[color:var(--importance-high)] text-xs m-0">{error}</p>
          {/if}
          <div class="flex gap-2 justify-end">
            <button class="bg-bg text-text py-1 px-3 text-[13px]" onclick={() => { creating = false; newName = ''; error = ''; }}>Cancel</button>
            <button class="bg-primary text-white py-1 px-3 text-[13px] disabled:opacity-50 disabled:cursor-default" onclick={handleCreate} disabled={submitting}>
              {submitting ? 'Creating...' : 'Create'}
            </button>
          </div>
        </div>
      {:else}
        <button class="block w-full text-left py-2.5 px-4 bg-none border-none border-t border-t-border rounded-none text-primary cursor-pointer text-sm font-semibold hover:bg-bg" onclick={() => creating = true}>+ New Board</button>
      {/if}
    </div>
  {/if}
</div>

<script lang="ts">
  interface Props {
    onfilter: (filterStr: string) => void;
    onsort: (sortStr: string) => void;
    initial?: string;
    initialSort?: string;
  }

  let { onfilter, onsort, initial, initialSort }: Props = $props();

  let filterOpen = $state(false);
  let sortOpen = $state(false);
  let filterValue = $state('');
  let sortValue = $state('');
  let lastAppliedFilter = '';
  let lastAppliedSort = '';
  let clearing = false;
  let prevInitial = $state<string | undefined>(undefined);
  let prevInitialSort = $state<string | undefined>(undefined);

  // Sync from parent props when they change externally
  $effect.pre(() => {
    if (initial !== prevInitial) {
      prevInitial = initial;
      filterValue = initial ?? '';
      lastAppliedFilter = filterValue;
    }
  });

  $effect.pre(() => {
    if (initialSort !== prevInitialSort) {
      prevInitialSort = initialSort;
      sortValue = initialSort ?? '';
      lastAppliedSort = sortValue;
    }
  });

  function applyFilter() {
    if (clearing) return;
    filterOpen = false;
    const v = filterValue.trim();
    if (v !== lastAppliedFilter) {
      lastAppliedFilter = v;
      onfilter(v);
    }
  }

  function applySort() {
    if (clearing) return;
    sortOpen = false;
    const v = sortValue.trim();
    if (v !== lastAppliedSort) {
      lastAppliedSort = v;
      onsort(v);
    }
  }

  function clearFilter() {
    clearing = true;
    filterValue = '';
    if (lastAppliedFilter !== '') {
      lastAppliedFilter = '';
      onfilter('');
    }
    setTimeout(() => clearing = false, 0);
  }

  function clearSort() {
    clearing = true;
    sortValue = '';
    if (lastAppliedSort !== '') {
      lastAppliedSort = '';
      onsort('');
    }
    setTimeout(() => clearing = false, 0);
  }

  function handleFilterKey(e: KeyboardEvent) {
    if (e.key === 'Enter') { applyFilter(); (e.target as HTMLInputElement).blur(); }
    if (e.key === 'Escape') clearFilter();
  }

  function handleSortKey(e: KeyboardEvent) {
    if (e.key === 'Enter') { applySort(); (e.target as HTMLInputElement).blur(); }
    if (e.key === 'Escape') clearSort();
  }

  // Close inputs when clicking outside the bar
  function handleClickOutside(e: MouseEvent) {
    const bar = (e.target as HTMLElement).closest('.bar');
    if (!bar) {
      if (filterOpen) applyFilter();
      if (sortOpen) applySort();
    }
  }

  $effect(() => {
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  });
</script>

<div class="bar">
  {#if filterOpen}
    <div class="pill-input active">
      <span class="pill-icon">&#9783;</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input
        type="text"
        bind:value={filterValue}
        onkeydown={handleFilterKey}
        onblur={applyFilter}
        placeholder="STATUS=NEW AND IMPORTANCE>=50 | CREATED_TIME>=-3600 (last hour)"
        title="Fields: STATUS, TITLE, IMPORTANCE, TAGS, ASSIGNEE, CREATED_TIME. Ops: = != > < >= <= ~=. Logic: AND OR NOT (). Time: relative with +/- seconds"
        autofocus
      />
      {#if filterValue}
        <button class="clear" onmousedown={(e) => { e.preventDefault(); clearFilter(); }}>x</button>
      {/if}
    </div>
  {:else}
    <button class="pill" class:has-value={!!filterValue} onclick={() => filterOpen = true}>
      <span class="pill-icon">&#9783;</span>
      {filterValue ? `Filter: ${filterValue}` : 'Filter'}
    </button>
  {/if}

  {#if sortOpen}
    <div class="pill-input active">
      <span class="pill-icon">&#8597;</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input
        type="text"
        bind:value={sortValue}
        onkeydown={handleSortKey}
        onblur={applySort}
        placeholder="IMPORTANCE desc, CREATED asc | Click column headers to sort"
        title="Fields: id, title, status, importance, effort, created, assignee. Dir: asc, desc"
        autofocus
      />
      {#if sortValue}
        <button class="clear" onmousedown={(e) => { e.preventDefault(); clearSort(); }}>x</button>
      {/if}
    </div>
  {:else}
    <button class="pill" class:has-value={!!sortValue} onclick={() => sortOpen = true}>
      <span class="pill-icon">&#8597;</span>
      {sortValue ? `Sort: ${sortValue}` : 'Sort'}
    </button>
  {/if}
</div>

<style>
  .bar {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 8px 0;
    margin-bottom: 12px;
    flex-wrap: wrap;
  }
  .pill {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 5px 12px;
    height: 30px;
    box-sizing: border-box;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 16px;
    font-size: 13px;
    color: var(--color-text-secondary);
    cursor: pointer;
    white-space: nowrap;
  }
  .pill:hover {
    border-color: var(--color-text-secondary);
    color: var(--color-text);
  }
  .pill.has-value {
    background: color-mix(in srgb, var(--color-primary) 25%, var(--color-bg));
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
  .pill-icon {
    font-size: 14px;
    line-height: 1;
  }
  .pill-input {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    background: var(--color-surface);
    border: 1.5px solid var(--color-primary);
    border-radius: 16px;
    flex: 1;
    min-width: 200px;
  }
  .pill-input input {
    flex: 1;
    border: none;
    outline: none;
    background: transparent;
    font-size: 13px;
    color: var(--color-text);
    font-family: monospace;
    padding: 2px 0;
  }
  .clear {
    background: none;
    border: none;
    color: var(--color-text-secondary);
    font-size: 14px;
    padding: 0 4px;
    cursor: pointer;
  }
  .clear:hover {
    color: var(--color-text);
  }
  @media (max-width: 768px) {
    .pill-input {
      min-width: 150px;
    }
  }
</style>

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

<div class="bar flex gap-2 items-center py-2 mb-3 flex-wrap">
  {#if filterOpen}
    <div class="inline-flex items-center gap-1.5 px-3 py-1 bg-surface border-[1.5px] border-primary rounded-2xl min-w-[150px] md:min-w-[200px] max-w-[500px]">
      <span class="text-sm leading-none">&#9783;</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input
        type="text"
        bind:value={filterValue}
        onkeydown={handleFilterKey}
        onblur={applyFilter}
        placeholder="STATUS=NEW, IMPORTANCE>=50"
        title="Fields: STATUS, TITLE, IMPORTANCE, TAGS, ASSIGNEE, CREATED_TIME. Ops: = != > < >= <= ~=. Logic: AND OR NOT (). Time: relative with +/- seconds"
        autofocus
        class="flex-1 border-none outline-none bg-transparent text-[13px] text-text font-mono py-0.5"
      />
      {#if filterValue}
        <button class="bg-none border-none text-text-secondary text-sm px-1 cursor-pointer hover:text-text" onmousedown={(e) => { e.preventDefault(); clearFilter(); }}>x</button>
      {/if}
    </div>
  {:else}
    <button class="pill flex items-center gap-1 px-3 py-[5px] h-[30px] box-border bg-bg border border-border rounded-2xl text-[13px] text-text-secondary cursor-pointer whitespace-nowrap hover:border-text-secondary hover:text-text {filterValue ? 'pill-has-value' : ''}" onclick={() => filterOpen = true}>
      <span class="text-sm leading-none">&#9783;</span>
      {filterValue ? `Filter: ${filterValue}` : 'Filter'}
    </button>
  {/if}

  {#if sortOpen}
    <div class="inline-flex items-center gap-1.5 px-3 py-1 bg-surface border-[1.5px] border-primary rounded-2xl min-w-[150px] md:min-w-[200px] max-w-[500px]">
      <span class="text-sm leading-none">&#8597;</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input
        type="text"
        bind:value={sortValue}
        onkeydown={handleSortKey}
        onblur={applySort}
        placeholder="IMPORTANCE desc, CREATED asc"
        title="Fields: id, title, status, importance, effort, created, assignee. Dir: asc, desc"
        autofocus
        class="flex-1 border-none outline-none bg-transparent text-[13px] text-text font-mono py-0.5"
      />
      {#if sortValue}
        <button class="bg-none border-none text-text-secondary text-sm px-1 cursor-pointer hover:text-text" onmousedown={(e) => { e.preventDefault(); clearSort(); }}>x</button>
      {/if}
    </div>
  {:else}
    <button class="pill flex items-center gap-1 px-3 py-[5px] h-[30px] box-border bg-bg border border-border rounded-2xl text-[13px] text-text-secondary cursor-pointer whitespace-nowrap hover:border-text-secondary hover:text-text {sortValue ? 'pill-has-value' : ''}" onclick={() => sortOpen = true}>
      <span class="text-sm leading-none">&#8597;</span>
      {sortValue ? `Sort: ${sortValue}` : 'Sort'}
    </button>
  {/if}
</div>

<style>
  .pill-has-value {
    background: color-mix(in srgb, var(--color-primary) 25%, var(--color-bg));
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
</style>

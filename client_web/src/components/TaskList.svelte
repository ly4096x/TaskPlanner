<script lang="ts">
  import type { Task } from '../lib/api';
  import { Icon, ChatBubbleLeft } from 'svelte-hero-icons';

  interface Props {
    tasks: Task[];
    onselect: (task: Task) => void;
    sortField?: string;
    sortDir?: 'asc' | 'desc';
    onsort?: (field: string) => void;
    unreadTaskIds?: Set<number>;
    onbatchmarkread?: (taskIds: number[]) => void;
  }

  let { tasks, onselect, sortField = 'id', sortDir = 'asc', onsort, unreadTaskIds = new Set(), onbatchmarkread }: Props = $props();

  let selected = $state<Set<number>>(new Set());

  let allSelected = $derived(tasks.length > 0 && tasks.every(t => selected.has(t.id)));

  function toggleSelect(taskId: number, e: Event) {
    e.stopPropagation();
    const next = new Set(selected);
    if (next.has(taskId)) next.delete(taskId);
    else next.add(taskId);
    selected = next;
  }

  function toggleAll() {
    if (allSelected) {
      selected = new Set();
    } else {
      selected = new Set(tasks.map(t => t.id));
    }
  }

  function clearSelection() {
    selected = new Set();
  }

  function handleBatchMarkRead() {
    if (onbatchmarkread) {
      onbatchmarkread([...selected]);
      selected = new Set();
    }
  }

  const COLUMNS: { key: string; label: string; sortable: boolean }[] = [
    { key: 'id', label: 'ID', sortable: true },
    { key: 'title', label: 'Title', sortable: true },
    { key: 'status', label: 'Status', sortable: true },
    { key: 'importance', label: 'Importance', sortable: true },
    { key: 'assignee_name', label: 'Assignee', sortable: true },
    { key: 'created_time', label: 'Created', sortable: true },
    { key: 'tags', label: 'Tags', sortable: false },
  ];

  function importanceColor(imp: number): string {
    if (imp >= 80) return 'var(--importance-high)';
    if (imp >= 50) return 'var(--importance-medium)';
    return 'var(--importance-low)';
  }

  function statusLabel(status: string): string {
    const abbrev: Record<string, string> = {
      WAITING_FOR_COMMAND_EXECUTION: 'WAITING EXEC',
      NOT_REPRODUCIBLE: 'NO REPRO',
    };
    return abbrev[status] ?? status.replace(/_/g, ' ');
  }

  function formatCreatedTime(ts: number): string {
    const now = Date.now() / 1000;
    const diff = now - ts;
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
    const d = new Date(ts * 1000);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  function statusCssVar(status: string): string {
    const map: Record<string, string> = {
      'WAITING_FOR_COMMAND_EXECUTION': 'waiting',
      'NOT_REPRODUCIBLE': 'not-reproducible',
    };
    return map[status] ?? status.toLowerCase();
  }

  function sortIndicator(key: string): string {
    if (sortField !== key) return '';
    return sortDir === 'asc' ? ' \u25B2' : ' \u25BC';
  }
</script>

<div class="overflow-x-auto relative">
  <table class="w-full border-collapse bg-transparent rounded-[--radius] overflow-hidden">
    <thead>
      <tr class="h-9 relative">
        <th class="px-2 border-b-2 border-border w-8 relative z-10">
          <input type="checkbox" checked={allSelected} onchange={toggleAll} class="cursor-pointer" />
        </th>
        {#each COLUMNS as col, i}
          {#if col.sortable && onsort}
            <th class="text-left px-4 text-xs font-semibold uppercase text-text-secondary border-b-2 border-border select-none cursor-pointer hover:text-text whitespace-nowrap {i >= 3 ? 'hidden md:table-cell' : ''} {selected.size > 0 ? 'invisible' : ''}"
              onclick={() => onsort(col.key)}>
              {col.label}{sortIndicator(col.key)}
            </th>
          {:else}
            <th class="text-left px-4 text-xs font-semibold uppercase text-text-secondary border-b-2 border-border select-none {i >= 3 ? 'hidden md:table-cell' : ''} {selected.size > 0 ? 'invisible' : ''}">{col.label}</th>
          {/if}
        {/each}
      </tr>
    </thead>
    {#if selected.size > 0}
      <div class="absolute top-0 left-10 right-0 h-9 flex items-center px-4 gap-3 bg-[color-mix(in_srgb,var(--color-primary)_10%,var(--color-bg))] border-b-2 border-primary z-0">
        <span class="text-sm text-primary font-semibold">{selected.size} selected</span>
        <button class="text-xs py-1 px-3 bg-primary text-white rounded font-semibold" onclick={handleBatchMarkRead}>Mark as Read</button>
        <button class="text-xs py-1 px-3 bg-bg text-text-secondary rounded" onclick={clearSelection}>Clear</button>
      </div>
    {/if}
    <tbody>
      {#each tasks as task (task.id)}
        <tr onclick={() => onselect(task)} class="cursor-pointer transition-[background] duration-100 hover:bg-bg {selected.has(task.id) ? '!bg-[color-mix(in_srgb,var(--color-primary)_8%,var(--color-surface))]' : ''}">
          <td class="py-1.5 px-2 border-b border-border w-8">
            <input type="checkbox" checked={selected.has(task.id)} onchange={(e) => toggleSelect(task.id, e)} onclick={(e) => e.stopPropagation()} class="cursor-pointer" />
          </td>
          <td class="py-1.5 px-4 border-b border-border text-sm text-text-secondary tabular-nums">#{task.id}</td>
          <td class="py-1.5 px-4 border-b border-border text-sm {unreadTaskIds.has(task.id) ? 'font-bold' : 'font-medium'}">
            {task.title}
            {#if task.text_comment_count > 0}
              <span class="ml-1.5 inline-flex items-center gap-0.5 text-[11px] text-text-secondary font-normal opacity-60" title="{task.text_comment_count} comment{task.text_comment_count > 1 ? 's' : ''}"><Icon src={ChatBubbleLeft} size="12" />{task.text_comment_count}</span>
            {/if}
          </td>
          <td class="py-1.5 px-4 border-b border-border text-sm">
            <span class="badge text-[11px] font-semibold py-0.5 px-2 rounded-xl uppercase whitespace-nowrap" style="--badge-color: var(--status-{statusCssVar(task.status)})">{statusLabel(task.status)}</span>
          </td>
          <td class="py-1.5 px-4 border-b border-border text-sm hidden md:table-cell">
            <span class="font-bold" style="color: {importanceColor(task.importance)}">{task.importance}</span>
          </td>
          <td class="py-1.5 px-4 border-b border-border text-sm text-text-secondary hidden md:table-cell {!task.assignee_name ? 'opacity-50 italic' : ''}">{task.assignee_name ?? 'Unassigned'}</td>
          <td class="py-1.5 px-4 border-b border-border text-xs text-text-secondary whitespace-nowrap hidden md:table-cell">
            {formatCreatedTime(task.created_time)}
          </td>
          <td class="py-1.5 px-4 border-b border-border text-sm hidden md:table-cell">
            <div class="flex flex-wrap gap-1">
              {#each task.tags as tag}
                <span class="bg-bg text-text-secondary text-xs py-0.5 px-2 rounded-xl">{tag}</span>
              {/each}
            </div>
          </td>
        </tr>
      {/each}
      {#if tasks.length === 0}
        <tr>
          <td colspan="8" class="text-center text-text-secondary py-10">No tasks found.</td>
        </tr>
      {/if}
    </tbody>
  </table>
</div>

<style>
  .badge {
    color: white;
    background: var(--badge-color);
  }
  :global([data-theme="dark"]) .badge {
    color: var(--badge-color);
    background: none;
    border: 1.5px solid var(--badge-color);
  }
</style>

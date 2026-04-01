<script lang="ts">
  import type { Task } from '../lib/api';

  interface Props {
    tasks: Task[];
    onselect: (task: Task) => void;
    sortField?: string;
    sortDir?: 'asc' | 'desc';
    onsort?: (field: string) => void;
  }

  let { tasks, onselect, sortField = 'id', sortDir = 'asc', onsort }: Props = $props();

  const COLUMNS: { key: string; label: string; sortable: boolean }[] = [
    { key: 'id', label: 'ID', sortable: true },
    { key: 'title', label: 'Title', sortable: true },
    { key: 'status', label: 'Status', sortable: true },
    { key: 'importance', label: 'Importance', sortable: true },
    { key: 'assignee_name', label: 'Assignee', sortable: true },
    { key: 'created_time', label: 'Created', sortable: true },
    { key: 'tags', label: 'Tags', sortable: false },
  ];

  function statusColor(status: Task['status']): string {
    switch (status) {
      case 'NEW': return 'var(--status-new)';
      case 'STARTED': return 'var(--status-started)';
      case 'WAITING_FOR_COMMAND_EXECUTION': return 'var(--status-waiting)';
      case 'BLOCKED': return 'var(--status-blocked)';
      case 'DONE': return 'var(--status-done)';
      case 'NOT_REPRODUCIBLE': return 'var(--status-not-reproducible)';
      case 'CANCELLED': return 'var(--status-cancelled)';
    }
  }

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

<div class="overflow-x-auto">
  <table class="w-full border-collapse bg-transparent rounded-[--radius] overflow-hidden">
    <thead>
      <tr>
        {#each COLUMNS as col, i}
          {#if col.sortable && onsort}
            <th class="text-left py-3 px-4 text-xs font-semibold uppercase text-text-secondary border-b-2 border-border select-none cursor-pointer hover:text-text {i >= 3 ? 'hidden md:table-cell' : ''} md:py-3 md:px-4 md:text-xs"
              onclick={() => onsort(col.key)}>
              {col.label}{sortIndicator(col.key)}
            </th>
          {:else}
            <th class="text-left py-3 px-4 text-xs font-semibold uppercase text-text-secondary border-b-2 border-border select-none {i >= 3 ? 'hidden md:table-cell' : ''}">{col.label}</th>
          {/if}
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each tasks as task (task.id)}
        <tr onclick={() => onselect(task)} class="cursor-pointer transition-[background] duration-100 hover:bg-bg">
          <td class="py-3 px-4 border-b border-border text-sm text-text-secondary tabular-nums">#{task.id}</td>
          <td class="py-3 px-4 border-b border-border text-sm font-medium">{task.title}</td>
          <td class="py-3 px-4 border-b border-border text-sm">
            <span class="badge text-[11px] font-semibold py-0.5 px-2 rounded-xl uppercase whitespace-nowrap" style="--badge-color: var(--status-{statusCssVar(task.status)})">{statusLabel(task.status)}</span>
          </td>
          <td class="py-3 px-4 border-b border-border text-sm hidden md:table-cell">
            <span class="font-bold" style="color: {importanceColor(task.importance)}">{task.importance}</span>
          </td>
          <td class="py-3 px-4 border-b border-border text-sm text-text-secondary hidden md:table-cell {!task.assignee_name ? 'opacity-50 italic' : ''}">{task.assignee_name ?? 'Unassigned'}</td>
          <td class="py-3 px-4 border-b border-border text-xs text-text-secondary whitespace-nowrap hidden md:table-cell">
            {formatCreatedTime(task.created_time)}
          </td>
          <td class="py-3 px-4 border-b border-border text-sm hidden md:table-cell">
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
          <td colspan="7" class="text-center text-text-secondary py-10">No tasks found.</td>
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

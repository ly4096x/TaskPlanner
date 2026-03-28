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

  function sortIndicator(key: string): string {
    if (sortField !== key) return '';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }
</script>

<div class="table-wrapper">
  <table>
    <thead>
      <tr>
        {#each COLUMNS as col}
          {#if col.sortable && onsort}
            <th class="sortable" onclick={() => onsort(col.key)}>
              {col.label}{sortIndicator(col.key)}
            </th>
          {:else}
            <th>{col.label}</th>
          {/if}
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each tasks as task (task.id)}
        <tr onclick={() => onselect(task)} class="row">
          <td class="id">#{task.id}</td>
          <td class="title">{task.title}</td>
          <td>
            <span class="badge badge-{task.status.toLowerCase()}">{statusLabel(task.status)}</span>
          </td>
          <td>
            <span class="importance" style="color: {importanceColor(task.importance)}">{task.importance}</span>
          </td>
          <td class="assignee" class:unassigned={!task.assignee_name}>{task.assignee_name ?? 'Unassigned'}</td>
          <td class="created">
            {formatCreatedTime(task.created_time)}
          </td>
          <td class="tags-cell">
            <div class="tags-wrap">
              {#each task.tags as tag}
                <span class="tag">{tag}</span>
              {/each}
            </div>
          </td>
        </tr>
      {/each}
      {#if tasks.length === 0}
        <tr>
          <td colspan="7" class="empty">No tasks found.</td>
        </tr>
      {/if}
    </tbody>
  </table>
</div>

<style>
  .table-wrapper {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    background: transparent;
    border-radius: var(--radius);
    overflow: hidden;
  }
  th {
    text-align: left;
    padding: 12px 16px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--color-text-secondary);
    border-bottom: 2px solid var(--color-border);
    user-select: none;
  }
  th.sortable {
    cursor: pointer;
  }
  th.sortable:hover {
    color: var(--color-text);
  }
  td {
    padding: 12px 16px;
    border-bottom: 1px solid var(--color-border);
    font-size: 14px;
  }
  .row {
    cursor: pointer;
    transition: background 0.1s;
  }
  .row:hover {
    background: var(--color-bg);
  }
  .id {
    color: var(--color-text-secondary);
    font-variant-numeric: tabular-nums;
  }
  .title {
    font-weight: 500;
  }
  .badge {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 12px;
    text-transform: uppercase;
    white-space: nowrap;
    color: white;
  }
  .badge-new { background: var(--status-new); }
  .badge-started { background: var(--status-started); }
  .badge-waiting_for_more_info,
  .badge-waiting_for_command_execution { background: var(--status-waiting); }
  .badge-blocked { background: var(--status-blocked); }
  .badge-done { background: var(--status-done); }
  .badge-not_reproducible { background: var(--status-not-reproducible); }
  .badge-cancelled { background: var(--status-cancelled); }
  :global([data-theme="dark"]) .badge {
    color: inherit;
    background: none;
    border: 1.5px solid;
  }
  :global([data-theme="dark"]) .badge-new { color: var(--status-new); border-color: var(--status-new); }
  :global([data-theme="dark"]) .badge-started { color: var(--status-started); border-color: var(--status-started); }
  :global([data-theme="dark"]) .badge-waiting_for_more_info,
  :global([data-theme="dark"]) .badge-waiting_for_command_execution { color: var(--status-waiting); border-color: var(--status-waiting); }
  :global([data-theme="dark"]) .badge-blocked { color: var(--status-blocked); border-color: var(--status-blocked); }
  :global([data-theme="dark"]) .badge-done { color: var(--status-done); border-color: var(--status-done); }
  :global([data-theme="dark"]) .badge-not_reproducible { color: var(--status-not-reproducible); border-color: var(--status-not-reproducible); }
  :global([data-theme="dark"]) .badge-cancelled { color: var(--status-cancelled); border-color: var(--status-cancelled); }
  .importance {
    font-weight: 700;
  }
  .assignee {
    color: var(--color-text-secondary);
  }
  .assignee.unassigned {
    color: var(--color-text-secondary);
    opacity: 0.5;
    font-style: italic;
  }
  .created {
    color: var(--color-text-secondary);
    font-size: 12px;
    white-space: nowrap;
  }
  .tags-cell {
  }
  .tags-cell .tags-wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .tag {
    background: var(--color-bg);
    color: var(--color-text-secondary);
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 12px;
  }
  .empty {
    text-align: center;
    color: var(--color-text-secondary);
    padding: 40px;
  }
  @media (max-width: 768px) {
    th:nth-child(n+4), td:nth-child(n+4) {
      display: none;
    }
    th {
      padding: 8px 10px;
      font-size: 11px;
    }
    td {
      padding: 8px 10px;
      font-size: 13px;
    }
  }
</style>

<script lang="ts">
  import type { Task } from '../lib/api';

  interface Props {
    task: Task;
    onclick: (task: Task) => void;
    minimal?: boolean;
  }

  let { task, onclick, minimal = false }: Props = $props();

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

  function statusCssVar(status: string): string {
    const map: Record<string, string> = {
      'WAITING_FOR_COMMAND_EXECUTION': 'waiting',
      'NOT_REPRODUCIBLE': 'not-reproducible',
    };
    return map[status] ?? status.toLowerCase();
  }
</script>

<button class="card" onclick={() => onclick(task)}
  style={minimal ? `background: color-mix(in srgb, var(--status-${statusCssVar(task.status)}) 8%, var(--color-surface))` : ''}>
  {#if minimal}
    <h3 class="title">{task.title}</h3>
    {#if task.assignee_name}
      <div class="assignee">{task.assignee_name}</div>
    {/if}
  {:else}
    <div class="card-header">
      <span class="badge badge-{task.status.toLowerCase()}">{statusLabel(task.status)}</span>
      <span class="importance" style="color: {importanceColor(task.importance)}">{task.importance}</span>
    </div>
    <h3 class="title">{task.title}</h3>
    {#if task.tags.length > 0}
      <div class="tags">
        {#each task.tags as tag}
          <span class="tag">{tag}</span>
        {/each}
      </div>
    {/if}
    {#if task.assignee_name}
      <div class="assignee">{task.assignee_name}</div>
    {/if}
  {/if}
</button>

<style>
  .card {
    background: var(--color-bg);
    border: none;
    border-radius: 8px;
    padding: 8px 10px;
    text-align: left;
    width: 100%;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    transition: background 0.15s;
  }
  .card:hover {
    background: color-mix(in srgb, var(--color-bg) 92%, var(--color-text));
    box-shadow: 0 2px 6px rgba(0,0,0,0.15);
  }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }
  .badge {
    font-size: 10px;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 10px;
    text-transform: uppercase;
    line-height: 14px;
    height: 16px;
    display: inline-flex;
    align-items: center;
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
    font-weight: 600;
    font-size: 12px;
  }
  .title {
    font-size: 14px;
    font-weight: 400;
    margin-bottom: 4px;
    color: var(--color-text);
    line-height: 1.3;
  }
  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 4px;
  }
  .tag {
    background: var(--color-bg);
    color: var(--color-text-secondary);
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 12px;
  }
  .assignee {
    font-size: 11px;
    color: var(--color-text-secondary);
    opacity: 0.5;
  }
</style>

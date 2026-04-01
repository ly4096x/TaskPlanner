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

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div class="bg-bg rounded-lg px-2.5 py-2 text-left w-full overflow-hidden shadow-[0_1px_2px_rgba(0,0,0,0.05)] transition-[background] duration-150 cursor-pointer hover:shadow-[0_2px_6px_rgba(0,0,0,0.15)] hover:brightness-[0.97]"
  onclick={() => onclick(task)}
  style={minimal ? `background: color-mix(in srgb, var(--status-${statusCssVar(task.status)}) 8%, var(--color-surface))` : ''}>
  {#if minimal}
    <h3 class="text-sm font-normal mb-1 text-text leading-tight break-words">{task.title}</h3>
    {#if task.assignee_name}
      <div class="text-[11px] text-text-secondary opacity-50">{task.assignee_name}</div>
    {/if}
  {:else}
    <div class="flex justify-between items-center mb-1">
      <span class="badge text-[10px] font-semibold px-1.5 py-px rounded-[10px] uppercase leading-[14px] h-4 inline-flex items-center whitespace-nowrap" style="--badge-color: var(--status-{statusCssVar(task.status)})">{statusLabel(task.status)}</span>
      <span class="font-semibold text-xs" style="color: {importanceColor(task.importance)}">{task.importance}</span>
    </div>
    <h3 class="text-sm font-normal mb-1 text-text leading-tight break-words">{task.title}</h3>
    {#if task.tags.length > 0}
      <div class="flex flex-wrap gap-1 mb-1">
        {#each task.tags as tag}
          <span class="bg-bg text-text-secondary text-[11px] px-1.5 py-px rounded-xl">{tag}</span>
        {/each}
      </div>
    {/if}
    {#if task.assignee_name}
      <div class="text-[11px] text-text-secondary opacity-50">{task.assignee_name}</div>
    {/if}
  {/if}
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

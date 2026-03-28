<script lang="ts">
  import type { Task } from '../lib/api';
  import { STATUSES, STATUS_LABELS } from '../lib/statuses';
  import TaskCard from './TaskCard.svelte';

  interface Props {
    tasks: Task[];
    onselect: (task: Task) => void;
    groupByStatus?: boolean;
    visibleStatuses?: Set<string>;
    statusOrder?: string[];
  }

  let { tasks, onselect, groupByStatus = true, visibleStatuses, statusOrder }: Props = $props();

  const STATUS_ORDER = [...STATUSES];

  // Load visible statuses from localStorage (fallback when no prop provided)
  function loadVisibleStatuses(): Set<string> {
    try {
      const saved = localStorage.getItem('kanbanVisibleStatuses');
      if (saved) return new Set(JSON.parse(saved));
    } catch {}
    // Default: show active statuses
    return new Set(['NEW', 'STARTED', 'BLOCKED', 'WAITING_FOR_COMMAND_EXECUTION']);
  }

  let internalVisibleStatuses = $state(loadVisibleStatuses());

  let effectiveVisibleStatuses = $derived(visibleStatuses ?? internalVisibleStatuses);

  function statusCssVar(status: string): string {
    const map: Record<string, string> = {
      'WAITING_FOR_COMMAND_EXECUTION': 'waiting',
      'NOT_REPRODUCIBLE': 'not-reproducible',
    };
    return map[status] ?? status.toLowerCase();
  }

  let grouped = $derived.by(() => {
    if (!groupByStatus) return null;
    const order = statusOrder ?? STATUS_ORDER;
    const groups: { status: Task['status']; label: string; tasks: Task[] }[] = [];
    for (const status of order) {
      if (!effectiveVisibleStatuses.has(status)) continue;
      const matching = tasks.filter(t => t.status === status);
      groups.push({ status, label: STATUS_LABELS[status], tasks: matching });
    }
    return groups;
  });
</script>

{#if tasks.length === 0 && !groupByStatus}
  <p class="empty">No tasks found.</p>
{:else if groupByStatus && grouped}
  <div class="kanban">
    {#each grouped as group (group.status)}
      <div class="kanban-col" style="background: color-mix(in srgb, var(--status-{statusCssVar(group.status)}) 8%, var(--color-bg))">
        <h3 class="col-header" style="color: var(--status-{statusCssVar(group.status)})">
          <span class="col-dot" style="background: var(--status-{statusCssVar(group.status)})"></span>
          {group.label}
        </h3>
        <div class="col-cards">
          {#each group.tasks as task (task.id)}
            <TaskCard {task} onclick={onselect} minimal />
          {/each}
        </div>
      </div>
    {/each}
  </div>
{:else}
  <div class="grid">
    {#each tasks as task (task.id)}
      <TaskCard {task} onclick={onselect} />
    {/each}
  </div>
{/if}

<style>
  .kanban {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding: 12px 16px 8px;
    align-items: flex-start;
    height: 100%;
  }
  .kanban-col {
    flex: 1;
    min-width: 240px;
    max-width: 320px;
    border-radius: 8px;
    padding: 2px 8px 6px;
  }
  .col-header {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 2px;
    padding-bottom: 0;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .col-cards {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-height: 20px;
  }
  .col-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
  }
  .empty {
    color: var(--color-text-secondary);
    text-align: center;
    padding: 40px;
  }
  @media (max-width: 768px) {
    .kanban {
      flex-direction: column;
      gap: 12px;
    }
    .kanban-col {
      max-width: none;
      min-width: auto;
    }
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>

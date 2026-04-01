<script lang="ts">
  import type { Task } from '../lib/api';
  import { STATUSES, STATUS_LABELS } from '../lib/statuses';
  import TaskCard from './TaskCard.svelte';

  interface Props {
    tasks: Task[];
    onselect: (task: Task) => void;
    onstatuschange?: (task: Task, newStatus: string) => void;
    groupByStatus?: boolean;
    visibleStatuses?: Set<string>;
    statusOrder?: string[];
  }

  let { tasks, onselect, onstatuschange, groupByStatus = true, visibleStatuses, statusOrder }: Props = $props();

  let dragOverStatus = $state<string | null>(null);

  function handleDragStart(e: DragEvent, task: Task) {
    e.dataTransfer!.effectAllowed = 'move';
    e.dataTransfer!.setData('text/plain', String(task.id));
  }

  function handleDragOver(e: DragEvent, status: string) {
    e.preventDefault();
    e.dataTransfer!.dropEffect = 'move';
    dragOverStatus = status;
  }

  function handleDragLeave(e: DragEvent, status: string) {
    // Only clear if leaving the column, not entering a child
    const related = e.relatedTarget as HTMLElement | null;
    if (!related || !(e.currentTarget as HTMLElement).contains(related)) {
      if (dragOverStatus === status) dragOverStatus = null;
    }
  }

  function handleDrop(e: DragEvent, targetStatus: string) {
    e.preventDefault();
    dragOverStatus = null;
    const taskId = parseInt(e.dataTransfer!.getData('text/plain'));
    const task = tasks.find(t => t.id === taskId);
    if (task && task.status !== targetStatus && onstatuschange) {
      onstatuschange(task, targetStatus);
    }
  }

  const STATUS_ORDER = [...STATUSES];

  function loadVisibleStatuses(): Set<string> {
    try {
      const saved = localStorage.getItem('kanbanVisibleStatuses');
      if (saved) return new Set(JSON.parse(saved));
    } catch {}
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
  <p class="text-text-secondary text-center py-10 px-10">No tasks found.</p>
{:else if groupByStatus && grouped}
  <div class="flex flex-col md:flex-row gap-3 md:gap-2 overflow-x-auto px-4 pt-3 pb-2 items-start h-full">
    {#each grouped as group (group.status)}
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div
        class="w-full md:flex-1 md:min-w-60 md:max-w-80 rounded-lg px-2 pt-0.5 pb-1.5 transition-[outline] duration-150 {dragOverStatus === group.status ? 'outline-2 outline-dashed outline-primary' : ''}"
        style="background: color-mix(in srgb, var(--status-{statusCssVar(group.status)}) 8%, var(--color-bg))"
        ondragover={(e) => handleDragOver(e, group.status)}
        ondragleave={(e) => handleDragLeave(e, group.status)}
        ondrop={(e) => handleDrop(e, group.status)}
      >
        <h3 class="text-sm font-semibold mb-0.5 flex items-center gap-2" style="color: var(--status-{statusCssVar(group.status)})">
          <span class="w-2 h-2 rounded-full inline-block shrink-0" style="background: var(--status-{statusCssVar(group.status)})"></span>
          {group.label}
          <span class="text-xs font-normal opacity-50">{group.tasks.length}</span>
        </h3>
        <div class="flex flex-col gap-2 min-h-5">
          {#each group.tasks as task (task.id)}
            <TaskCard {task} onclick={onselect} minimal draggable={!!onstatuschange} ondragstart={(e) => handleDragStart(e, task)} />
          {/each}
        </div>
      </div>
    {/each}
  </div>
{:else}
  <div class="grid grid-cols-1 md:grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
    {#each tasks as task (task.id)}
      <TaskCard {task} onclick={onselect} />
    {/each}
  </div>
{/if}

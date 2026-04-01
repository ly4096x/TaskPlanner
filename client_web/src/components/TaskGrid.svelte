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

  // Mouse-based drag state
  let draggingTask = $state<Task | null>(null);
  let dragOverStatus = $state<string | null>(null);
  let dragGhost = $state<HTMLElement | null>(null);

  function handleMouseDown(e: MouseEvent, task: Task) {
    if (!onstatuschange) return;
    // Only left mouse button
    if (e.button !== 0) return;

    const startX = e.clientX;
    const startY = e.clientY;
    let started = false;

    function onMove(ev: MouseEvent) {
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;

      // Require 5px movement to start drag (avoid accidental drags on click)
      if (!started && Math.abs(dx) + Math.abs(dy) < 5) return;

      if (!started) {
        started = true;
        draggingTask = task;
        document.body.classList.add('select-none');

        // Create ghost element
        const ghost = document.createElement('div');
        ghost.textContent = task.title;
        ghost.className = 'fixed pointer-events-none z-[9999] bg-surface border border-primary rounded-lg px-3 py-2 text-sm shadow-lg opacity-80 max-w-60 truncate';
        document.body.appendChild(ghost);
        dragGhost = ghost;
      }

      if (dragGhost) {
        dragGhost.style.left = `${ev.clientX + 12}px`;
        dragGhost.style.top = `${ev.clientY + 12}px`;
      }

      // Detect which column we're over
      const el = document.elementFromPoint(ev.clientX, ev.clientY);
      const col = el?.closest('[data-status]') as HTMLElement | null;
      dragOverStatus = col?.dataset.status ?? null;
    }

    function onUp() {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.classList.remove('select-none');

      if (dragGhost) {
        dragGhost.remove();
        dragGhost = null;
      }

      if (started && draggingTask && dragOverStatus && dragOverStatus !== draggingTask.status) {
        onstatuschange!(draggingTask, dragOverStatus);
      }

      draggingTask = null;
      dragOverStatus = null;
    }

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
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
      <div
        class="w-full md:flex-1 md:min-w-60 md:max-w-80 rounded-lg px-2 pt-0.5 pb-1.5 transition-[outline] duration-150 {dragOverStatus === group.status ? 'outline-2 outline-dashed outline-primary' : ''}"
        style="background: color-mix(in srgb, var(--status-{statusCssVar(group.status)}) 8%, var(--color-bg))"
        data-status={group.status}
      >
        <h3 class="text-sm font-semibold mb-0.5 flex items-center gap-2" style="color: var(--status-{statusCssVar(group.status)})">
          <span class="w-2 h-2 rounded-full inline-block shrink-0" style="background: var(--status-{statusCssVar(group.status)})"></span>
          {group.label}
          <span class="text-xs font-normal opacity-50">{group.tasks.length}</span>
        </h3>
        <div class="flex flex-col gap-2 min-h-5">
          {#each group.tasks as task (task.id)}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div onmousedown={(e) => handleMouseDown(e, task)} class="{onstatuschange ? 'cursor-grab' : ''}">
              <TaskCard {task} onclick={onselect} minimal />
            </div>
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

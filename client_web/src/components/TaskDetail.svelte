<script lang="ts">
  import { editTask, listUsers, listTasks, getTask as fetchTask, getAttachments, uploadFile, deleteAttachment, getFileUrl, type Task, type User, type Attachment, type EditTaskData } from '../lib/api';
  import { TRANSITIONS, TRANSITION_CONDITIONS } from '../lib/statuses';
  import { marked } from 'marked';
  import CommentSection from './CommentSection.svelte';

  marked.setOptions({ breaks: true });

  interface Props {
    task: Task;
    boardId: number;
    currentUserId?: number | null;
    onclose: () => void;
    onupdated: (task: Task) => void;
  }

  let { task, boardId, currentUserId, onclose, onupdated }: Props = $props();

  let editingField = $state<string | null>(null);
  let editTitle = $state('');
  let editDescription = $state('');
  let editImportance = $state(0);
  let editEffort = $state<number | null>(null);
  let editStatus = $state<Task['status']>('NEW');
  let editTags = $state<string[]>([]);
  let editBlockers = $state<number[]>([]);
  let editAssigneeId = $state<number | null>(null);
  let editParentId = $state<string>('');
  let editStatusReason = $state('');

  $effect.pre(() => {
    editTitle = task.title;
    editDescription = task.description;
    editImportance = task.importance;
    editEffort = task.estimated_effort;
    editStatus = task.status;
    editTags = [...task.tags];
    editBlockers = [...task.blockers];
    editAssigneeId = task.assignee_id;
    editParentId = task.parent_task_id != null ? String(task.parent_task_id) : '';
    editStatusReason = '';
  });

  // Statuses reachable from the task's current status per the shared
  // transition graph (self included so the select always has a valid value) —
  // the same graph the server enforces, so illegal targets can't be picked.
  const statusOptions = $derived([task.status, ...(TRANSITIONS[task.status] ?? [])]);

  // Transitions into these statuses need a status_reason server-side
  // (non-admins for DONE/WAITING/CANCELLED; everyone for NOT_REPRODUCIBLE).
  const REASON_STATUSES = ['DONE', 'WAITING_FOR_COMMAND_EXECUTION', 'NOT_REPRODUCIBLE', 'CANCELLED'];
  const statusChanged = $derived(editStatus !== task.status);
  const reasonPrefix = $derived(
    (TRANSITION_CONDITIONS[editStatus] as { require_reason?: string } | undefined)?.require_reason ?? ''
  );
  const showReasonField = $derived(statusChanged && REASON_STATUSES.includes(editStatus));

  function handleStatusChange() {
    // Prefill the mandatory prefix (e.g. "Not reproducible because:") so the
    // user completes the sentence instead of discovering the 422 on save.
    if (reasonPrefix && !editStatusReason.startsWith(reasonPrefix)) {
      editStatusReason = `${reasonPrefix} `;
    }
    markDirty();
  }
  let newTag = $state('');
  let newBlocker = $state('');
  let saving = $state(false);
  let saveError = $state('');
  let users: User[] = $state([]);
  let dirty = $state(false);
  let attachments: Attachment[] = $state([]);
  let uploading = $state(false);
  let subtasks: Task[] = $state([]);
  let parentTask: Task | null = $state(null);

  async function loadSubtasks() {
    try {
      subtasks = await listTasks(boardId, `PARENT=${task.id}`);
    } catch { /* ignore */ }
  }

  async function loadParent() {
    if (task.parent_task_id) {
      try {
        parentTask = await fetchTask(boardId, task.parent_task_id);
      } catch { parentTask = null; }
    } else {
      parentTask = null;
    }
  }

  async function loadUsers() {
    try {
      users = await listUsers();
    } catch { /* ignore */ }
  }

  async function loadAttachments() {
    try {
      attachments = await getAttachments(boardId, task.id);
    } catch { /* ignore */ }
  }

  async function handleFileUpload(files: FileList | File[]) {
    if (!files.length) return;
    uploading = true;
    try {
      for (const file of files) {
        await uploadFile(boardId, task.id, file);
      }
      await loadAttachments();
    } catch (e) {
      console.error('Upload failed:', e);
    } finally {
      uploading = false;
    }
  }

  function handleFileInput(e: Event) {
    const input = e.target as HTMLInputElement;
    if (input.files) handleFileUpload(input.files);
    input.value = '';
  }

  async function handleDeleteAttachment(id: number) {
    try {
      await deleteAttachment(id);
      attachments = attachments.filter(a => a.id !== id);
    } catch (e) {
      console.error('Delete failed:', e);
    }
  }

  function handlePaste(e: ClipboardEvent) {
    const items = e.clipboardData?.items;
    if (!items) return;
    const files: File[] = [];
    for (const item of items) {
      if (item.kind === 'file') {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }
    if (files.length) {
      e.preventDefault();
      handleFileUpload(files);
    }
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    if (e.dataTransfer?.files.length) {
      handleFileUpload(e.dataTransfer.files);
    }
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function markDirty() {
    dirty = true;
  }

  async function save() {
    saving = true;
    saveError = '';
    try {
      const selectedUser = users.find(u => u.id === editAssigneeId);
      const parentVal = editParentId.trim();
      const parentTaskId = parentVal === '' || parentVal === '0' ? null : parseInt(parentVal);
      const payload: EditTaskData = {
        title: editTitle,
        description: editDescription,
        importance: editImportance,
        estimated_effort: editEffort,
        status: editStatus,
        tags: editTags,
        blockers: editBlockers,
        assignee: selectedUser?.username ?? null,
        parent_task_id: parentTaskId,
      };
      if (statusChanged && editStatusReason.trim()) {
        let reason = editStatusReason.trim();
        if (reasonPrefix && !reason.startsWith(reasonPrefix)) {
          reason = `${reasonPrefix} ${reason}`;
        }
        payload.status_reason = reason;
      }
      const updated = await editTask(boardId, task.id, payload);
      dirty = false;
      onupdated(updated);
    } catch (e) {
      saveError = e instanceof Error ? e.message : 'Save failed';
    } finally {
      saving = false;
    }
  }

  function addTag() {
    const t = newTag.trim();
    if (t && !editTags.includes(t)) {
      editTags = [...editTags, t];
      markDirty();
    }
    newTag = '';
  }

  function removeTag(tag: string) {
    editTags = editTags.filter(t => t !== tag);
    markDirty();
  }

  function addBlocker() {
    const id = parseInt(newBlocker);
    if (!isNaN(id) && !editBlockers.includes(id)) {
      editBlockers = [...editBlockers, id];
      markDirty();
    }
    newBlocker = '';
  }

  function removeBlocker(id: number) {
    editBlockers = editBlockers.filter(b => b !== id);
    markDirty();
  }

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

  function formatTime(ts: number): string {
    return new Date(ts * 1000).toLocaleString();
  }

  loadUsers();
  loadAttachments();
  loadSubtasks();
  loadParent();
  // Mark task as read (logs access time server-side)
  $effect(() => {
    fetchTask(boardId, task.id).catch(() => {});
  });
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="fixed inset-0 bg-black/40 flex justify-end z-[100]" onclick={onclose} role="presentation">
  <!-- svelte-ignore a11y_no_static_element_interactions a11y_interactive_supports_focus a11y_click_events_have_key_events -->
  <div class="bg-surface w-full md:w-[min(70vw,1200px)] h-full overflow-y-auto p-6 md:p-6 shadow-[-4px_0_24px_rgba(0,0,0,0.15)]" onclick={(e) => e.stopPropagation()} onpaste={handlePaste} ondrop={handleDrop} ondragover={handleDragOver} role="dialog" aria-label="Task detail" tabindex="-1">
    <div class="flex justify-between items-center mb-5 md:mb-5">
      <span class="text-lg font-bold text-text-secondary">#{task.id}</span>
      <button class="bg-bg py-1.5 px-3 font-semibold text-text-secondary" onclick={onclose}>X</button>
    </div>

    <div class="mb-4">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label class="text-xs font-semibold uppercase text-text-secondary mb-1 block">Title</label>
      {#if editingField === 'title'}
        <input
          type="text"
          bind:value={editTitle}
          onblur={() => { editingField = null; markDirty(); }}
          onkeydown={(e) => { if (e.key === 'Enter') { editingField = null; markDirty(); } }}
          class="w-full box-border"
        />
      {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="py-2 px-3 border border-dashed border-border rounded-[--radius] cursor-pointer text-[15px] transition-[border-color] duration-100 relative hover:border-primary after:content-['\270E'] after:absolute after:top-2 after:right-2 after:text-sm after:text-text-secondary after:opacity-40 after:transition-opacity after:duration-150 hover:after:opacity-80" onclick={() => editingField = 'title'}>{editTitle}</div>
      {/if}
    </div>

    <div class="mb-4">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label class="text-xs font-semibold uppercase text-text-secondary mb-1 block">Status</label>
      <select bind:value={editStatus} onchange={handleStatusChange}>
        {#each statusOptions as s}
          <option value={s}>{s.replace(/_/g, ' ')}</option>
        {/each}
      </select>
      <span class="inline-block w-2.5 h-2.5 rounded-full ml-2 align-middle" style="background: {statusColor(editStatus)}"></span>
      {#if showReasonField}
        <input
          type="text"
          bind:value={editStatusReason}
          oninput={markDirty}
          placeholder={reasonPrefix ? `${reasonPrefix} …` : 'Reason for status change'}
          title="Recorded as a comment. Required for non-admins (always for NOT REPRODUCIBLE)."
          class="w-full box-border mt-2"
        />
      {/if}
    </div>

    <div class="mb-4">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label class="text-xs font-semibold uppercase text-text-secondary mb-1 block">Description</label>
      {#if editingField === 'description'}
        <div class="border border-border rounded-[--radius] overflow-hidden focus-within:border-primary">
          <textarea
            bind:value={editDescription}
            onblur={() => { editingField = null; markDirty(); }}
            rows="4"
            class="border-none rounded-none w-full focus:outline-none focus:shadow-none"
          ></textarea>
          <div class="flex items-center py-1 px-2 border-t border-border bg-bg">
            <label class="cursor-pointer text-text-secondary text-[13px] py-1 px-2 border border-dashed border-border rounded-[--radius] hover:text-primary hover:border-primary">
              <input type="file" multiple onchange={handleFileInput} style="display:none" />
              Attach files
            </label>
          </div>
        </div>
      {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="py-2 px-3 border border-dashed border-border rounded-[--radius] cursor-pointer text-[15px] transition-[border-color] duration-100 relative min-h-10 text-text prose prose-sm dark:prose-invert max-w-none hover:border-primary after:content-['\270E'] after:absolute after:top-2 after:right-2 after:text-sm after:text-text-secondary after:opacity-40 after:transition-opacity after:duration-150 hover:after:opacity-80" onclick={() => editingField = 'description'}>
          {#if editDescription}
            {@html marked.parse(editDescription)}
          {:else}
            (none)
          {/if}
        </div>
      {/if}
    </div>

    <div class="flex flex-col md:flex-row gap-4 md:gap-4">
      <div class="mb-4 flex-1">
        <!-- svelte-ignore a11y_label_has_associated_control -->
        <label class="text-xs font-semibold uppercase text-text-secondary mb-1 block">Importance: {editImportance}</label>
        <input type="range" min="0" max="100" bind:value={editImportance} onchange={markDirty} class="border-none p-0 w-full" />
      </div>
      <div class="mb-4 flex-1">
        <!-- svelte-ignore a11y_label_has_associated_control -->
        <label class="text-xs font-semibold uppercase text-text-secondary mb-1 block">Effort</label>
        <input type="number" min="0" step="0.5" bind:value={editEffort} onchange={markDirty} class="w-full box-border" />
      </div>
    </div>

    <div class="mb-4">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label class="text-xs font-semibold uppercase text-text-secondary mb-1 block">Assignee</label>
      <select bind:value={editAssigneeId} onchange={markDirty}>
        <option value={null}>Unassigned</option>
        {#each users as user (user.id)}
          <option value={user.id}>{user.display_name}</option>
        {/each}
      </select>
    </div>

    <div class="mb-4">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label class="text-xs font-semibold uppercase text-text-secondary mb-1 block">Tags</label>
      <div class="flex flex-wrap gap-1.5 items-center">
        {#each editTags as tag}
          <span class="bg-bg py-1 px-2.5 rounded-xl text-[13px] flex items-center gap-1">
            {tag}
            <button type="button" class="bg-none p-0 px-0.5 text-xs text-text-secondary" onclick={() => removeTag(tag)}>x</button>
          </span>
        {/each}
        <input
          type="text"
          bind:value={newTag}
          placeholder="Add tag..."
          onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } }}
          class="w-[100px] border border-dashed border-border text-[13px] py-1 px-2"
        />
      </div>
    </div>

    <div class="mb-4">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label class="text-xs font-semibold uppercase text-text-secondary mb-1 block">Blocked By</label>
      <div class="flex flex-wrap gap-1.5 items-center">
        {#each editBlockers as id}
          <span class="bg-bg py-1 px-2.5 rounded-xl text-[13px] flex items-center gap-1">
            #{id}
            <button type="button" class="bg-none p-0 px-0.5 text-xs text-text-secondary" onclick={() => removeBlocker(id)}>x</button>
          </span>
        {/each}
        <input
          type="text"
          bind:value={newBlocker}
          placeholder="Task ID..."
          onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addBlocker(); } }}
          class="w-[100px] border border-dashed border-border text-[13px] py-1 px-2"
        />
      </div>
    </div>

    <div class="mb-4">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label class="text-xs font-semibold uppercase text-text-secondary mb-1 block">Created</label>
      <div class="text-sm text-text-secondary">{formatTime(task.created_time)}</div>
    </div>

    <div class="mb-4">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label class="text-xs font-semibold uppercase text-text-secondary mb-1 block">Parent Task {#if parentTask}<span class="font-normal text-[11px] text-text-secondary normal-case tracking-normal">#{parentTask.id} -- {parentTask.title}</span>{/if}</label>
      <input type="text" bind:value={editParentId} onchange={markDirty} placeholder="Task ID (empty to clear)" class="w-full box-border" />
    </div>

    {#if subtasks.length > 0}
      <div class="mb-4">
        <!-- svelte-ignore a11y_label_has_associated_control -->
        <label class="text-xs font-semibold uppercase text-text-secondary mb-1 block">Subtasks ({subtasks.length})</label>
        <div class="flex flex-col gap-1">
          {#each subtasks as st (st.id)}
            <div class="flex items-center gap-2 text-sm py-1 text-text-secondary">
              <span class="inline-block w-2.5 h-2.5 rounded-full" style="background: {statusColor(st.status)}"></span>
              #{st.id} -- {st.title}
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if attachments.length > 0}
      <div class="mb-4">
        <!-- svelte-ignore a11y_label_has_associated_control -->
        <label class="text-xs font-semibold uppercase text-text-secondary mb-1 block">Attachments</label>
        <div class="flex flex-col gap-2">
          {#each attachments as att (att.id)}
            <div class="flex flex-col gap-1 p-2 bg-bg rounded-[--radius]">
              {#if att.content_type.startsWith('image/')}
                <a href={getFileUrl(att.id)} target="_blank" rel="noopener">
                  <img src={getFileUrl(att.id)} alt={att.original_name} class="max-w-[300px] max-h-[200px] rounded-[--radius] object-contain cursor-pointer" />
                </a>
              {:else}
                <a href={getFileUrl(att.id)} target="_blank" rel="noopener" class="text-primary no-underline text-sm hover:underline">
                  {att.original_name}
                </a>
              {/if}
              <div class="flex items-center gap-2 text-xs text-text-secondary">
                <span class="flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{att.original_name}</span>
                <span class="whitespace-nowrap">{formatSize(att.size)}</span>
                <button type="button" class="bg-none py-0.5 px-1.5 text-xs text-text-secondary cursor-pointer hover:text-[color:var(--importance-high)]" onclick={() => handleDeleteAttachment(att.id)}>x</button>
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if saveError}
      <div class="save-error border border-[color:var(--importance-high)] rounded-[--radius] text-[color:var(--importance-high)] py-2 px-3 text-[13px] mb-2">
        {saveError}
      </div>
    {/if}

    {#if dirty}
      <div class="sticky bottom-0 py-3 bg-surface border-t border-border text-right">
        <button class="bg-primary text-white py-2.5 px-6 font-semibold hover:bg-primary-hover disabled:opacity-50 disabled:cursor-default" onclick={save} disabled={saving}>
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    {/if}

    <CommentSection {boardId} taskId={task.id} />
  </div>
</div>

<style>
  .save-error {
    background: color-mix(in srgb, var(--importance-high) 10%, var(--color-surface));
  }
</style>

<script lang="ts">
  import { editTask, listUsers, listTasks, getTask as fetchTask, getAttachments, uploadFile, deleteAttachment, getFileUrl, type Task, type User, type Attachment } from '../lib/api';
  import { STATUSES } from '../lib/statuses';
  import { marked } from 'marked';
  import CommentSection from './CommentSection.svelte';

  marked.setOptions({ breaks: true });

  interface Props {
    task: Task;
    boardId: number;
    currentUserId?: number | null;
    currentUsername?: string | null;
    onclose: () => void;
    onupdated: (task: Task) => void;
  }

  let { task, boardId, currentUserId, currentUsername, onclose, onupdated }: Props = $props();

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

  // Sync edit fields from task prop
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
  });
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
      // Find the selected user's username for the assignee field
      const selectedUser = users.find(u => u.id === editAssigneeId);
      const parentVal = editParentId.trim();
      const parentTaskId = parentVal === '' || parentVal === '0' ? null : parseInt(parentVal);
      const updated = await editTask(boardId, task.id, {
        title: editTitle,
        description: editDescription,
        importance: editImportance,
        estimated_effort: editEffort,
        status: editStatus,
        tags: editTags,
        blockers: editBlockers,
        assignee: selectedUser?.username ?? null,
        parent_task_id: parentTaskId,
      }, currentUsername);
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
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="overlay" onclick={onclose} role="presentation">
  <!-- svelte-ignore a11y_no_static_element_interactions a11y_interactive_supports_focus a11y_click_events_have_key_events -->
  <div class="panel" onclick={(e) => e.stopPropagation()} onpaste={handlePaste} ondrop={handleDrop} ondragover={handleDragOver} role="dialog" aria-label="Task detail" tabindex="-1">
    <div class="panel-header">
      <span class="task-id">#{task.id}</span>
      <button class="close-btn" onclick={onclose}>X</button>
    </div>

    <div class="field">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label>Title</label>
      {#if editingField === 'title'}
        <input
          type="text"
          bind:value={editTitle}
          onblur={() => { editingField = null; markDirty(); }}
          onkeydown={(e) => { if (e.key === 'Enter') { editingField = null; markDirty(); } }}
        />
      {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="editable" onclick={() => editingField = 'title'}>{editTitle}</div>
      {/if}
    </div>

    <div class="field">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label>Status</label>
      <select bind:value={editStatus} onchange={markDirty}>
        {#each STATUSES as s}
          <option value={s}>{s.replace(/_/g, ' ')}</option>
        {/each}
      </select>
      <span class="status-dot" style="background: {statusColor(editStatus)}"></span>
    </div>

    <div class="field">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label>Description</label>
      {#if editingField === 'description'}
        <div class="desc-box">
          <textarea
            bind:value={editDescription}
            onblur={() => { editingField = null; markDirty(); }}
            rows="4"
          ></textarea>
          <div class="desc-box-toolbar">
            <label class="attach-btn-inline">
              <input type="file" multiple onchange={handleFileInput} style="display:none" />
              Attach files
            </label>
          </div>
        </div>
      {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="editable desc" onclick={() => editingField = 'description'}>
          {#if editDescription}
            {@html marked.parse(editDescription)}
          {:else}
            (none)
          {/if}
        </div>
      {/if}
    </div>

    <div class="row">
      <div class="field half">
        <!-- svelte-ignore a11y_label_has_associated_control -->
        <label>Importance: {editImportance}</label>
        <input type="range" min="0" max="100" bind:value={editImportance} onchange={markDirty} />
      </div>
      <div class="field half">
        <!-- svelte-ignore a11y_label_has_associated_control -->
        <label>Effort</label>
        <input type="number" min="0" step="0.5" bind:value={editEffort} onchange={markDirty} />
      </div>
    </div>

    <div class="field">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label>Assignee</label>
      <select bind:value={editAssigneeId} onchange={markDirty}>
        <option value={null}>Unassigned</option>
        {#each users as user (user.id)}
          <option value={user.id}>{user.display_name}</option>
        {/each}
      </select>
    </div>

    <div class="field">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label>Tags</label>
      <div class="chips">
        {#each editTags as tag}
          <span class="chip">
            {tag}
            <button type="button" class="chip-remove" onclick={() => removeTag(tag)}>x</button>
          </span>
        {/each}
        <input
          type="text"
          bind:value={newTag}
          placeholder="Add tag..."
          onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } }}
          class="chip-input"
        />
      </div>
    </div>

    <div class="field">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label>Blocked By</label>
      <div class="chips">
        {#each editBlockers as id}
          <span class="chip">
            #{id}
            <button type="button" class="chip-remove" onclick={() => removeBlocker(id)}>x</button>
          </span>
        {/each}
        <input
          type="text"
          bind:value={newBlocker}
          placeholder="Task ID..."
          onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addBlocker(); } }}
          class="chip-input"
        />
      </div>
    </div>

    <div class="field">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label>Created</label>
      <div class="meta">{formatTime(task.created_time)}</div>
    </div>

    <div class="field">
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label>Parent Task {#if parentTask}<span class="parent-hint">#{parentTask.id} — {parentTask.title}</span>{/if}</label>
      <input type="text" bind:value={editParentId} onchange={markDirty} placeholder="Task ID (empty to clear)" />
    </div>

    {#if subtasks.length > 0}
      <div class="field">
        <!-- svelte-ignore a11y_label_has_associated_control -->
        <label>Subtasks ({subtasks.length})</label>
        <div class="subtask-list">
          {#each subtasks as st (st.id)}
            <div class="subtask-item">
              <span class="status-dot" style="background: {statusColor(st.status)}"></span>
              #{st.id} — {st.title}
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if attachments.length > 0}
      <div class="field">
        <!-- svelte-ignore a11y_label_has_associated_control -->
        <label>Attachments</label>
        <div class="attachments">
          {#each attachments as att (att.id)}
            <div class="attachment-item">
              {#if att.content_type.startsWith('image/')}
                <a href={getFileUrl(att.id)} target="_blank" rel="noopener">
                  <img src={getFileUrl(att.id)} alt={att.original_name} class="attachment-thumb" />
                </a>
              {:else}
                <a href={getFileUrl(att.id)} target="_blank" rel="noopener" class="attachment-file">
                  {att.original_name}
                </a>
              {/if}
              <div class="attachment-info">
                <span class="attachment-name">{att.original_name}</span>
                <span class="attachment-size">{formatSize(att.size)}</span>
                <button type="button" class="attachment-delete" onclick={() => handleDeleteAttachment(att.id)}>x</button>
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if saveError}
      <div class="save-error">{saveError}</div>
    {/if}

    {#if dirty}
      <div class="save-bar">
        <button class="save-btn" onclick={save} disabled={saving}>
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    {/if}

    <CommentSection {boardId} taskId={task.id} commenterUsername={currentUsername ?? null} />
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.4);
    display: flex;
    justify-content: flex-end;
    z-index: 100;
  }
  .panel {
    background: var(--color-surface);
    width: min(70vw, 1200px);
    height: 100%;
    overflow-y: auto;
    padding: 24px;
    box-shadow: -4px 0 24px rgba(0,0,0,0.15);
  }
  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
  }
  .task-id {
    font-size: 18px;
    font-weight: 700;
    color: var(--color-text-secondary);
  }
  .close-btn {
    background: var(--color-bg);
    padding: 6px 12px;
    font-weight: 600;
    color: var(--color-text-secondary);
  }
  .field {
    margin-bottom: 16px;
  }
  .field label {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--color-text-secondary);
    margin-bottom: 4px;
    display: block;
  }
  .editable {
    padding: 8px 12px;
    border: 1px dashed var(--color-border);
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 15px;
    transition: border-color 0.1s;
    position: relative;
  }
  .editable::after {
    content: '\270E';
    position: absolute;
    top: 8px;
    right: 8px;
    font-size: 14px;
    color: var(--color-text-secondary);
    opacity: 0.4;
    transition: opacity 0.15s;
  }
  .editable:hover {
    border-color: var(--color-primary);
  }
  .editable:hover::after {
    opacity: 0.8;
  }
  .field input[type="text"],
  .field textarea {
    width: 100%;
    box-sizing: border-box;
  }
  .desc-box {
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .desc-box:focus-within {
    border-color: var(--color-primary);
  }
  .desc-box textarea {
    border: none;
    border-radius: 0;
    width: 100%;
  }
  .desc-box textarea:focus {
    outline: none;
    box-shadow: none;
  }
  .desc-box-toolbar {
    display: flex;
    align-items: center;
    padding: 4px 8px;
    border-top: 1px solid var(--color-border);
    background: var(--color-bg);
  }
  .attach-btn-inline {
    cursor: pointer;
    color: var(--color-text-secondary);
    font-size: 13px;
    padding: 4px 8px;
    border: 1px dashed var(--color-border);
    border-radius: var(--radius);
  }
  .attach-btn-inline:hover {
    color: var(--color-primary);
    border-color: var(--color-primary);
  }
  .desc {
    min-height: 40px;
    color: var(--color-text);
  }
  .desc :global(p) {
    margin: 0 0 8px;
  }
  .desc :global(p:last-child) {
    margin-bottom: 0;
  }
  .desc :global(code) {
    background: var(--color-bg);
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 13px;
  }
  .desc :global(pre) {
    background: var(--color-bg);
    padding: 8px 12px;
    border-radius: var(--radius);
    overflow-x: auto;
    font-size: 13px;
  }
  .desc :global(pre code) {
    background: none;
    padding: 0;
  }
  .row {
    display: flex;
    gap: 16px;
  }
  .half {
    flex: 1;
  }
  input[type="range"] {
    border: none;
    padding: 0;
    width: 100%;
  }
  .status-dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    margin-left: 8px;
    vertical-align: middle;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }
  .chip {
    background: var(--color-bg);
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .chip-remove {
    background: none;
    padding: 0 2px;
    font-size: 12px;
    color: var(--color-text-secondary);
  }
  .chip-input {
    width: 100px;
    border: 1px dashed var(--color-border);
    font-size: 13px;
    padding: 4px 8px;
  }
  .meta {
    font-size: 14px;
    color: var(--color-text-secondary);
  }
  .parent-hint {
    font-weight: 400;
    font-size: 11px;
    color: var(--color-text-secondary);
    text-transform: none;
    letter-spacing: normal;
  }
  .subtask-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .subtask-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    padding: 4px 0;
    color: var(--color-text-secondary);
  }
  .save-error {
    background: color-mix(in srgb, var(--importance-high) 10%, var(--color-surface));
    border: 1px solid var(--importance-high);
    border-radius: var(--radius);
    color: var(--importance-high);
    padding: 8px 12px;
    font-size: 13px;
    margin-bottom: 8px;
  }
  .save-bar {
    position: sticky;
    bottom: 0;
    padding: 12px 0;
    background: var(--color-surface);
    border-top: 1px solid var(--color-border);
    text-align: right;
  }
  .save-btn {
    background: var(--color-primary);
    color: white;
    padding: 10px 24px;
    font-weight: 600;
  }
  .save-btn:hover:not(:disabled) {
    background: var(--color-primary-hover);
  }
  .save-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .attachments {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .attachment-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px;
    background: var(--color-bg);
    border-radius: var(--radius);
  }
  .attachment-thumb {
    max-width: 300px;
    max-height: 200px;
    border-radius: var(--radius);
    object-fit: contain;
    cursor: pointer;
  }
  .attachment-file {
    color: var(--color-primary);
    text-decoration: none;
    font-size: 14px;
  }
  .attachment-file:hover {
    text-decoration: underline;
  }
  .attachment-info {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--color-text-secondary);
  }
  .attachment-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .attachment-size {
    white-space: nowrap;
  }
  .attachment-delete {
    background: none;
    padding: 2px 6px;
    font-size: 12px;
    color: var(--color-text-secondary);
    cursor: pointer;
  }
  .attachment-delete:hover {
    color: var(--importance-high, red);
  }
  .upload-area {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    border: 2px dashed var(--color-border);
    border-radius: var(--radius);
    color: var(--color-text-secondary);
    font-size: 13px;
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .upload-area:hover {
    border-color: var(--color-primary);
  }
  @media (max-width: 768px) {
    .panel {
      width: 100%;
      max-width: none;
    }
    .panel-header {
      margin-bottom: 12px;
    }
    .row {
      flex-direction: column;
      gap: 0;
    }
  }
</style>

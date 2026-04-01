<script lang="ts">
  import { createTask, listUsers, listTags, uploadFile, type User, type Tag, type Task } from '../lib/api';

  interface Props {
    boardId: number;
    currentUserId?: number | null;
    oncreated: (task: Task) => void;
    oncancel: () => void;
  }

  let { boardId, currentUserId, oncreated, oncancel }: Props = $props();

  let title = $state('');
  let description = $state('');
  let importance = $state(0);
  let estimatedEffort = $state(0);
  let assigneeUsername = $state<string | null>(null);
  let parentTaskId = $state<number | null>(null);
  let tagInput = $state('');
  let tags: string[] = $state([]);
  let submitting = $state(false);
  let error = $state('');
  let pendingFiles: File[] = $state([]);

  let users: User[] = $state([]);
  let availableTags: Tag[] = $state([]);
  let loadingData = $state(true);

  async function loadData() {
    try {
      const results = await Promise.race([
        Promise.all([listUsers(), listTags(boardId)]),
        new Promise<never>((_, reject) => setTimeout(() => reject(new Error('timeout')), 5000)),
      ]);
      [users, availableTags] = results;
    } catch {
      // Non-critical — form works without users/tags
    } finally {
      loadingData = false;
    }
  }

  function addTag() {
    const t = tagInput.trim();
    if (t && !tags.includes(t)) {
      tags = [...tags, t];
    }
    tagInput = '';
  }

  function removeTag(tag: string) {
    tags = tags.filter(t => t !== tag);
  }

  function handleTagKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      addTag();
    }
  }

  function handleFileInput(e: Event) {
    const input = e.target as HTMLInputElement;
    if (input.files) {
      pendingFiles = [...pendingFiles, ...input.files];
    }
    input.value = '';
  }

  function removePendingFile(index: number) {
    pendingFiles = pendingFiles.filter((_, i) => i !== index);
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
      pendingFiles = [...pendingFiles, ...files];
    }
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    if (e.dataTransfer?.files.length) {
      pendingFiles = [...pendingFiles, ...e.dataTransfer.files];
    }
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
  }

  async function handleSubmit() {
    if (!title.trim()) {
      error = 'Title is required';
      return;
    }
    error = '';
    submitting = true;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      const task = await createTask(boardId, {
        title: title.trim(),
        description: description.trim(),
        importance,
        estimated_effort: estimatedEffort,
        assignee: assigneeUsername,
        tags,
        parent_task_id: parentTaskId,
      });
      clearTimeout(timeout);

      // Upload pending files after task creation
      for (const file of pendingFiles) {
        try {
          await uploadFile(boardId, task.id, file);
        } catch (e) {
          console.error('File upload failed:', e);
        }
      }

      oncreated(task);
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        error = 'Request timed out. Please try again.';
      } else {
        error = e instanceof Error ? e.message : 'Failed to create task';
      }
    } finally {
      submitting = false;
    }
  }

  loadData();
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="overlay" onclick={oncancel} role="presentation">
  <!-- svelte-ignore a11y_no_static_element_interactions a11y_interactive_supports_focus a11y_click_events_have_key_events -->
  <div class="panel" onclick={(e) => e.stopPropagation()} onpaste={handlePaste} ondrop={handleDrop} ondragover={handleDragOver} role="dialog" aria-label="Create task" tabindex="-1">
    <div class="panel-header">
      <h2>New Task</h2>
      <button class="close-btn" onclick={oncancel}>X</button>
    </div>

    <form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
      <label>
        Title *
        <input type="text" bind:value={title} placeholder="Task title" required />
      </label>

      <label>
        Description
        <div class="desc-box">
          <textarea bind:value={description} placeholder="Describe the task..." rows="3"></textarea>
          <div class="desc-box-toolbar">
            <label class="attach-btn-inline">
              <input type="file" multiple onchange={handleFileInput} style="display:none" />
              Attach files
            </label>
          </div>
        </div>
      </label>

      <div class="row">
        <label class="half">
          Importance: {importance}
          <input type="range" min="0" max="100" bind:value={importance} />
        </label>
        <label class="half">
          Estimated Effort
          <input type="number" min="0" step="0.5" bind:value={estimatedEffort} />
        </label>
      </div>

      <label>
        Assignee {#if loadingData}<span class="loading-hint">(loading...)</span>{/if}
        <select bind:value={assigneeUsername}>
          <option value={null}>Unassigned</option>
          {#each users as user (user.id)}
            <option value={user.username}>{user.display_name}</option>
          {/each}
        </select>
      </label>

      <label>
        Parent Task
        <input type="number" min="0" bind:value={parentTaskId} placeholder="Parent task ID (optional)" />
      </label>

      <label>
        Tags
        <div class="tag-input">
          <div class="tag-chips">
            {#each tags as tag}
              <span class="tag-chip">
                {tag}
                <button type="button" class="remove-tag" onclick={() => removeTag(tag)}>x</button>
              </span>
            {/each}
          </div>
          <input
            type="text"
            bind:value={tagInput}
            onkeydown={handleTagKeydown}
            placeholder="Type and press Enter"
          />
          {#if availableTags.length > 0}
            <div class="tag-suggestions">
              {#each availableTags.filter(t => !tags.includes(t.name)) as tag (tag.id)}
                <button type="button" class="tag-suggestion" onclick={() => { tags = [...tags, tag.name]; }}>
                  + {tag.name}
                </button>
              {/each}
            </div>
          {/if}
        </div>
      </label>

      {#if pendingFiles.length > 0}
        <div class="file-upload">
          {#each pendingFiles as file, i}
            <div class="pending-file">
              <span class="pending-file-name">{file.name}</span>
              <button type="button" class="remove-file" onclick={() => removePendingFile(i)}>x</button>
            </div>
          {/each}
        </div>
      {/if}

      {#if error}
        <p class="error">{error}</p>
      {/if}

      <div class="actions">
        <button type="submit" class="submit" disabled={submitting}>
          {submitting ? 'Creating...' : 'Create Task'}
        </button>
      </div>
    </form>
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
  .close-btn {
    background: var(--color-bg);
    padding: 6px 12px;
    font-weight: 600;
    color: var(--color-text-secondary);
  }
  h2 {
    font-size: 20px;
  }
  form {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 13px;
    font-weight: 600;
    color: var(--color-text-secondary);
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
    font-weight: 400;
  }
  .attach-btn-inline:hover {
    color: var(--color-primary);
    border-color: var(--color-primary);
  }
  .tag-input {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .tag-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .tag-chip {
    background: var(--color-bg);
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .remove-tag {
    background: none;
    padding: 0 2px;
    font-size: 12px;
    color: var(--color-text-secondary);
  }
  .tag-suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .tag-suggestion {
    background: var(--color-bg);
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 12px;
    color: var(--color-primary);
  }
  .loading-hint {
    font-weight: 400;
    font-size: 11px;
    color: var(--color-text-secondary);
  }
  .error {
    color: var(--importance-high);
    font-size: 14px;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 8px;
  }
  .submit {
    background: var(--color-primary);
    color: white;
  }
  .submit:hover:not(:disabled) {
    background: var(--color-primary-hover);
  }
  .submit:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .file-upload {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .pending-file {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 8px;
    background: var(--color-bg);
    border-radius: var(--radius);
    font-size: 13px;
  }
  .pending-file-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--color-text);
    font-weight: 400;
  }
  .remove-file {
    background: none;
    padding: 0 4px;
    font-size: 12px;
    color: var(--color-text-secondary);
    cursor: pointer;
  }
  .upload-area {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 12px;
    border: 2px dashed var(--color-border);
    border-radius: var(--radius);
    color: var(--color-text-secondary);
    font-size: 13px;
    font-weight: 400;
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .upload-area:hover {
    border-color: var(--color-primary);
  }
</style>

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
<div class="fixed inset-0 bg-black/40 flex justify-end z-[100]" onclick={oncancel} role="presentation">
  <!-- svelte-ignore a11y_no_static_element_interactions a11y_interactive_supports_focus a11y_click_events_have_key_events -->
  <div class="bg-surface w-[min(70vw,1200px)] h-full overflow-y-auto p-6 shadow-[-4px_0_24px_rgba(0,0,0,0.15)]" onclick={(e) => e.stopPropagation()} onpaste={handlePaste} ondrop={handleDrop} ondragover={handleDragOver} role="dialog" aria-label="Create task" tabindex="-1">
    <div class="flex justify-between items-center mb-5">
      <h2 class="text-xl">New Task</h2>
      <button class="bg-bg py-1.5 px-3 font-semibold text-text-secondary" onclick={oncancel}>X</button>
    </div>

    <form class="flex flex-col gap-4" onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
      <label class="flex flex-col gap-1 text-[13px] font-semibold text-text-secondary">
        Title *
        <input type="text" bind:value={title} placeholder="Task title" required />
      </label>

      <label class="flex flex-col gap-1 text-[13px] font-semibold text-text-secondary">
        Description
        <div class="border border-border rounded-[--radius] overflow-hidden focus-within:border-primary">
          <textarea bind:value={description} placeholder="Describe the task..." rows="3" class="border-none rounded-none w-full focus:outline-none focus:shadow-none"></textarea>
          <div class="flex items-center py-1 px-2 border-t border-border bg-bg">
            <label class="cursor-pointer text-text-secondary text-[13px] py-1 px-2 border border-dashed border-border rounded-[--radius] font-normal hover:text-primary hover:border-primary">
              <input type="file" multiple onchange={handleFileInput} style="display:none" />
              Attach files
            </label>
          </div>
        </div>
      </label>

      <div class="flex gap-4">
        <label class="flex-1 flex flex-col gap-1 text-[13px] font-semibold text-text-secondary">
          Importance: {importance}
          <input type="range" min="0" max="100" bind:value={importance} class="border-none p-0" />
        </label>
        <label class="flex-1 flex flex-col gap-1 text-[13px] font-semibold text-text-secondary">
          Estimated Effort
          <input type="number" min="0" step="0.5" bind:value={estimatedEffort} />
        </label>
      </div>

      <label class="flex flex-col gap-1 text-[13px] font-semibold text-text-secondary">
        Assignee {#if loadingData}<span class="font-normal text-[11px] text-text-secondary">(loading...)</span>{/if}
        <select bind:value={assigneeUsername}>
          <option value={null}>Unassigned</option>
          {#each users as user (user.id)}
            <option value={user.username}>{user.display_name}</option>
          {/each}
        </select>
      </label>

      <label class="flex flex-col gap-1 text-[13px] font-semibold text-text-secondary">
        Parent Task
        <input type="number" min="0" bind:value={parentTaskId} placeholder="Parent task ID (optional)" />
      </label>

      <label class="flex flex-col gap-1 text-[13px] font-semibold text-text-secondary">
        Tags
        <div class="flex flex-col gap-1.5">
          <div class="flex flex-wrap gap-1">
            {#each tags as tag}
              <span class="bg-bg py-0.5 px-2 rounded-xl text-xs flex items-center gap-1">
                {tag}
                <button type="button" class="bg-none p-0 px-0.5 text-xs text-text-secondary" onclick={() => removeTag(tag)}>x</button>
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
            <div class="flex flex-wrap gap-1">
              {#each availableTags.filter(t => !tags.includes(t.name)) as tag (tag.id)}
                <button type="button" class="bg-bg text-xs py-0.5 px-2 rounded-xl text-primary" onclick={() => { tags = [...tags, tag.name]; }}>
                  + {tag.name}
                </button>
              {/each}
            </div>
          {/if}
        </div>
      </label>

      {#if pendingFiles.length > 0}
        <div class="flex flex-col gap-1.5">
          {#each pendingFiles as file, i}
            <div class="flex items-center gap-2 py-1 px-2 bg-bg rounded-[--radius] text-[13px]">
              <span class="flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-text font-normal">{file.name}</span>
              <button type="button" class="bg-none p-0 px-1 text-xs text-text-secondary cursor-pointer" onclick={() => removePendingFile(i)}>x</button>
            </div>
          {/each}
        </div>
      {/if}

      {#if error}
        <p class="text-[color:var(--importance-high)] text-sm">{error}</p>
      {/if}

      <div class="flex justify-end gap-2 mt-2">
        <button type="submit" class="bg-primary text-white hover:bg-primary-hover disabled:opacity-50 disabled:cursor-default" disabled={submitting}>
          {submitting ? 'Creating...' : 'Create Task'}
        </button>
      </div>
    </form>
  </div>
</div>

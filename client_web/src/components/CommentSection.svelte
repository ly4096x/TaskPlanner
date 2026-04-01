<script lang="ts">
  import { getComments, addComment, getAttachments, uploadCommentFile, getFileUrl, type Comment, type Attachment } from '../lib/api';
  import { marked } from 'marked';

  marked.setOptions({ breaks: true });

  interface Props {
    boardId: number;
    taskId: number;
    commenterUsername?: string | null;
  }

  let { boardId, taskId, commenterUsername }: Props = $props();

  let comments: Comment[] = $state([]);
  let newComment = $state('');
  let loading = $state(false);
  let loadError = $state('');
  let submitting = $state(false);
  let pendingFiles: File[] = $state([]);
  let commentAttachments: Record<number, Attachment[]> = $state({});
  let commentSort: 'oldest' | 'newest' = $state(
    (localStorage.getItem('commentSort') as 'oldest' | 'newest') || 'oldest'
  );

  let sortedComments = $derived(
    commentSort === 'newest' ? [...comments].reverse() : comments
  );

  async function loadComments() {
    loading = true;
    loadError = '';
    try {
      comments = await getComments(boardId, taskId);
      const allAttachments = await getAttachments(boardId, taskId);
      const grouped: Record<number, Attachment[]> = {};
      for (const att of allAttachments) {
        if (att.comment_id) {
          (grouped[att.comment_id] ??= []).push(att);
        }
      }
      commentAttachments = grouped;
    } catch (e) {
      loadError = e instanceof Error ? e.message : 'Failed to load comments';
    } finally {
      loading = false;
    }
  }

  async function handleSubmit() {
    if (!newComment.trim() && pendingFiles.length === 0) return;
    submitting = true;
    try {
      const text = newComment.trim() || (pendingFiles.length > 0 ? `(${pendingFiles.length} file${pendingFiles.length > 1 ? 's' : ''} attached)` : '');
      const comment = await addComment(boardId, taskId, text, commenterUsername);
      if (pendingFiles.length > 0) {
        const uploaded: Attachment[] = [];
        for (const file of pendingFiles) {
          const att = await uploadCommentFile(boardId, taskId, comment.id, file);
          uploaded.push(att);
        }
        commentAttachments = { ...commentAttachments, [comment.id]: uploaded };
      }
      comments = [...comments, comment];
      newComment = '';
      pendingFiles = [];
    } finally {
      submitting = false;
    }
  }

  function handleFileSelect(e: Event) {
    const input = e.target as HTMLInputElement;
    if (input.files) {
      pendingFiles = [...pendingFiles, ...Array.from(input.files)];
    }
    input.value = '';
  }

  function removePendingFile(index: number) {
    pendingFiles = pendingFiles.filter((_, i) => i !== index);
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatTime(ts: number): string {
    return new Date(ts * 1000).toLocaleString();
  }

  $effect(() => {
    taskId;
    loadComments();
  });
</script>

<div class="mt-6">
  <div class="flex items-center justify-between mb-3">
    <h4 class="text-base">Comments</h4>
    {#if comments.length > 1}
      <button class="bg-bg text-text-secondary text-xs py-[3px] px-2.5 border border-border rounded-[--radius] hover:text-text" onclick={() => { commentSort = commentSort === 'oldest' ? 'newest' : 'oldest'; localStorage.setItem('commentSort', commentSort); }}>
        {commentSort === 'oldest' ? '\u2193 Oldest' : '\u2191 Newest'}
      </button>
    {/if}
  </div>

  {#snippet commentList()}
    {#if loading}
      <p class="text-text-secondary text-sm py-2">Loading comments...</p>
    {:else if loadError}
      <p class="text-[color:var(--importance-high)] text-sm py-2">{loadError}</p>
      <button class="bg-bg text-text text-[13px] py-1 px-3 mb-3" onclick={loadComments}>Retry</button>
    {:else if comments.length === 0}
      <p class="text-text-secondary text-sm py-2">No comments yet.</p>
    {:else}
      <div class="flex flex-col gap-2 mb-4">
        {#each sortedComments as comment (comment.id)}
          <div class="bg-bg rounded-[--radius] py-2.5 px-3.5 {comment.comment_type === 'METADATA_CHANGE' ? 'metadata-comment' : ''} {comment.comment_type === 'EXECUTION_LOG' ? 'log-comment' : ''} {comment.comment_type === 'TEXT' ? 'text-comment' : ''}">
            <div class="text-xs text-text-secondary mb-1 {comment.comment_type !== 'TEXT' ? 'text-[11px] mb-0.5' : ''}">{#if comment.commenter_name}<span class="font-semibold text-text">{comment.commenter_name}</span> &middot; {/if}{formatTime(comment.created_time)}</div>
            <div class="prose prose-sm max-w-none {comment.comment_type === 'METADATA_CHANGE' ? 'text-xs text-text-secondary' : ''} {comment.comment_type === 'EXECUTION_LOG' ? 'text-[13px] text-text-secondary' : ''} {comment.comment_type === 'TEXT' ? '!text-text' : ''}">
              {@html marked.parse(comment.content)}
            </div>
            {#if commentAttachments[comment.id]?.length}
              <div class="flex flex-wrap gap-2 mt-2">
                {#each commentAttachments[comment.id] as att (att.id)}
                  {#if att.content_type.startsWith('image/')}
                    <a href={getFileUrl(att.id)} target="_blank" rel="noopener">
                      <img src={getFileUrl(att.id)} alt={att.original_name} class="max-w-[200px] max-h-[120px] rounded-[--radius] object-contain cursor-pointer" />
                    </a>
                  {:else}
                    <a href={getFileUrl(att.id)} target="_blank" rel="noopener" class="text-primary no-underline text-[13px] hover:underline">
                      {att.original_name} <span class="text-text-secondary text-xs">({formatSize(att.size)})</span>
                    </a>
                  {/if}
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/snippet}

  {#if commentSort === 'newest'}
    {@render commentForm()}
    {@render commentList()}
  {:else}
    {@render commentList()}
    {@render commentForm()}
  {/if}

  {#snippet commentForm()}
    <form class="flex flex-col gap-2" onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
      <div class="border border-border rounded-[--radius] overflow-hidden focus-within:border-primary">
        <textarea
          bind:value={newComment}
          placeholder="Add a comment..."
          rows="2"
          class="border-none rounded-none resize-y w-full focus:outline-none focus:shadow-none"
        ></textarea>
        <div class="flex items-center py-1 px-2 border-t border-border bg-bg">
          <label class="cursor-pointer text-text-secondary text-[13px] py-1 px-2 border border-dashed border-border rounded-[--radius] hover:text-primary hover:border-primary">
            <input type="file" multiple onchange={handleFileSelect} style="display:none" />
            Attach files
          </label>
        </div>
      </div>
      {#if pendingFiles.length > 0}
        <div class="flex flex-wrap gap-1.5">
          {#each pendingFiles as file, i}
            <span class="bg-bg py-[3px] px-2 rounded-xl text-xs flex items-center gap-1">
              {file.name}
              <button type="button" class="bg-none p-0 px-0.5 text-[11px] text-text-secondary cursor-pointer" onclick={() => removePendingFile(i)}>x</button>
            </span>
          {/each}
        </div>
      {/if}
      <div class="flex justify-end items-center">
        <button type="submit" class="bg-primary text-white hover:bg-primary-hover disabled:opacity-50 disabled:cursor-default" disabled={submitting || (!newComment.trim() && pendingFiles.length === 0)}>
          {submitting ? 'Adding...' : 'Add Comment'}
        </button>
      </div>
    </form>
  {/snippet}
</div>

<style>
  .metadata-comment {
    background: color-mix(in srgb, var(--status-waiting) 10%, var(--color-surface));
    border-left: 3px solid var(--status-waiting);
    font-family: monospace;
    font-size: 12px;
    color: var(--color-text-secondary);
    padding: 6px 14px;
  }
  .text-comment {
    background: color-mix(in srgb, var(--status-started) 8%, var(--color-surface));
    border-left: 3px solid var(--status-started);
    color: var(--color-text);
  }
  .log-comment {
    font-size: 13px;
    color: var(--color-text-secondary);
    padding: 6px 14px;
  }
</style>

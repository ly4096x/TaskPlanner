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

<div class="comments">
  <div class="comments-header">
    <h4>Comments</h4>
    {#if comments.length > 1}
      <button class="sort-toggle" onclick={() => { commentSort = commentSort === 'oldest' ? 'newest' : 'oldest'; localStorage.setItem('commentSort', commentSort); }}>
        {commentSort === 'oldest' ? '↓ Oldest' : '↑ Newest'}
      </button>
    {/if}
  </div>

  {#if loading}
    <p class="loading">Loading comments...</p>
  {:else if loadError}
    <p class="error">{loadError}</p>
    <button class="retry-btn" onclick={loadComments}>Retry</button>
  {:else if comments.length === 0}
    <p class="empty">No comments yet.</p>
  {:else}
    <div class="comment-list">
      {#each sortedComments as comment (comment.id)}
        <div class="comment" class:metadata-comment={comment.comment_type === 'METADATA_CHANGE'} class:log-comment={comment.comment_type === 'EXECUTION_LOG'}>
          <div class="comment-meta">{#if comment.commenter_name}<span class="commenter">{comment.commenter_name}</span> · {/if}{formatTime(comment.created_time)}</div>
          <div class="comment-content">
            {@html marked.parse(comment.content)}
          </div>
          {#if commentAttachments[comment.id]?.length}
            <div class="comment-attachments">
              {#each commentAttachments[comment.id] as att (att.id)}
                {#if att.content_type.startsWith('image/')}
                  <a href={getFileUrl(att.id)} target="_blank" rel="noopener">
                    <img src={getFileUrl(att.id)} alt={att.original_name} class="comment-thumb" />
                  </a>
                {:else}
                  <a href={getFileUrl(att.id)} target="_blank" rel="noopener" class="comment-file">
                    {att.original_name} <span class="file-size">({formatSize(att.size)})</span>
                  </a>
                {/if}
              {/each}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  <form class="comment-form" onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
    <textarea
      bind:value={newComment}
      placeholder="Add a comment..."
      rows="2"
    ></textarea>
    {#if pendingFiles.length > 0}
      <div class="pending-files">
        {#each pendingFiles as file, i}
          <span class="pending-file">
            {file.name}
            <button type="button" class="pending-remove" onclick={() => removePendingFile(i)}>x</button>
          </span>
        {/each}
      </div>
    {/if}
    <div class="comment-actions">
      <label class="attach-btn">
        <input type="file" multiple onchange={handleFileSelect} style="display:none" />
        Attach files
      </label>
      <button type="submit" disabled={submitting || (!newComment.trim() && pendingFiles.length === 0)}>
        {submitting ? 'Adding...' : 'Add Comment'}
      </button>
    </div>
  </form>
</div>

<style>
  .comments {
    margin-top: 24px;
  }
  .comments-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  h4 {
    font-size: 16px;
  }
  .sort-toggle {
    background: var(--color-bg);
    color: var(--color-text-secondary);
    font-size: 12px;
    padding: 3px 10px;
    border: 1px solid var(--color-border);
  }
  .sort-toggle:hover {
    color: var(--color-text);
  }
  .error {
    color: var(--importance-high);
    font-size: 14px;
    padding: 8px 0;
  }
  .retry-btn {
    background: var(--color-bg);
    color: var(--color-text);
    font-size: 13px;
    padding: 4px 12px;
    margin-bottom: 12px;
  }
  .loading, .empty {
    color: var(--color-text-secondary);
    font-size: 14px;
    padding: 8px 0;
  }
  .comment-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
  }
  .comment {
    background: var(--color-bg);
    border-radius: var(--radius);
    padding: 10px 14px;
  }
  .comment.metadata-comment {
    background: color-mix(in srgb, var(--status-waiting) 10%, var(--color-surface));
    border-left: 3px solid var(--status-waiting);
    font-family: monospace;
    font-size: 12px;
    color: var(--color-text-secondary);
    padding: 6px 14px;
  }
  .comment.metadata-comment .comment-meta {
    font-size: 11px;
    margin-bottom: 2px;
  }
  .comment.metadata-comment .comment-content {
    font-size: 12px;
    color: var(--color-text-secondary);
  }
  .comment.log-comment {
    background: color-mix(in srgb, var(--status-started) 8%, var(--color-surface));
    border-left: 3px solid var(--status-started);
    font-size: 13px;
    padding: 6px 14px;
  }
  .comment.log-comment .comment-meta {
    font-size: 11px;
    margin-bottom: 2px;
  }
  .comment.log-comment .comment-content {
    font-size: 13px;
    color: var(--color-text-secondary);
  }
  .comment-meta {
    font-size: 12px;
    color: var(--color-text-secondary);
    margin-bottom: 4px;
  }
  .commenter {
    font-weight: 600;
    color: var(--color-text);
  }
  .comment-content {
    font-size: 14px;
  }
  .comment-content :global(p) {
    margin: 0 0 8px;
  }
  .comment-content :global(p:last-child) {
    margin-bottom: 0;
  }
  .comment-content :global(code) {
    background: var(--color-bg);
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 13px;
  }
  .comment-content :global(pre) {
    background: var(--color-bg);
    padding: 8px 12px;
    border-radius: var(--radius);
    overflow-x: auto;
    font-size: 13px;
  }
  .comment-content :global(pre code) {
    background: none;
    padding: 0;
  }
  .comment-attachments {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
  }
  .comment-thumb {
    max-width: 200px;
    max-height: 120px;
    border-radius: var(--radius);
    object-fit: contain;
    cursor: pointer;
  }
  .comment-file {
    color: var(--color-primary);
    text-decoration: none;
    font-size: 13px;
  }
  .comment-file:hover {
    text-decoration: underline;
  }
  .file-size {
    color: var(--color-text-secondary);
    font-size: 12px;
  }
  .comment-form {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .comment-form textarea {
    resize: vertical;
  }
  .comment-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .comment-actions button {
    background: var(--color-primary);
    color: white;
  }
  .comment-actions button:hover:not(:disabled) {
    background: var(--color-primary-hover);
  }
  .comment-actions button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .attach-btn {
    cursor: pointer;
    color: var(--color-text-secondary);
    font-size: 13px;
    padding: 4px 8px;
    border: 1px dashed var(--color-border);
    border-radius: var(--radius);
  }
  .attach-btn:hover {
    color: var(--color-primary);
    border-color: var(--color-primary);
  }
  .pending-files {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .pending-file {
    background: var(--color-bg);
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .pending-remove {
    background: none;
    padding: 0 2px;
    font-size: 11px;
    color: var(--color-text-secondary);
    cursor: pointer;
  }
</style>

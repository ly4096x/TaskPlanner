<script lang="ts">
  import { listUsers, createUser, editUser, deleteUser, type User } from '../lib/api';

  interface Props {
    onclose: () => void;
  }

  let { onclose }: Props = $props();

  let users: User[] = $state([]);
  let loading = $state(true);
  let error = $state('');
  let showForm = $state(false);
  let newExternalId = $state('');
  let newUsername = $state('');
  let newName = $state('');
  let creating = $state(false);
  let createError = $state('');
  let editingId = $state<number | null>(null);
  let editName = $state('');
  let editUsername = $state('');
  let editExternalId = $state('');
  let saving = $state(false);
  let collapsed = $state<Set<number>>(new Set());

  async function loadUsers() {
    loading = true;
    error = '';
    try {
      users = await listUsers();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load users';
    } finally {
      loading = false;
    }
  }

  let userTree = $derived.by(() => {
    const childrenMap = new Map<number | null, User[]>();
    for (const u of users) {
      const parent = u.report_to ?? null;
      if (!childrenMap.has(parent)) childrenMap.set(parent, []);
      childrenMap.get(parent)!.push(u);
    }
    return childrenMap;
  });

  let rootUsers = $derived((userTree.get(null) ?? []).sort((a, b) => a.id - b.id));

  function getChildren(userId: number): User[] {
    return (userTree.get(userId) ?? []).sort((a, b) => a.id - b.id);
  }

  function hasChildren(userId: number): boolean {
    return (userTree.get(userId) ?? []).length > 0;
  }

  function toggleCollapse(userId: number) {
    const next = new Set(collapsed);
    if (next.has(userId)) next.delete(userId);
    else next.add(userId);
    collapsed = next;
  }

  async function handleCreate() {
    if (!newExternalId.trim() || !newName.trim()) {
      createError = 'External ID and name are required';
      return;
    }
    if (newUsername && !/^[a-z][a-z0-9_]*[a-z0-9]$/.test(newUsername)) {
      createError = 'Username must be a-z only, min 3 chars';
      return;
    }
    creating = true;
    createError = '';
    try {
      const data: any = { external_id: newExternalId.trim(), display_name: newName.trim() };
      if (newUsername.trim()) data.username = newUsername.trim();
      const user = await createUser(data);
      users = [...users, user];
      newExternalId = '';
      newUsername = '';
      newName = '';
      showForm = false;
    } catch (e) {
      createError = e instanceof Error ? e.message : 'Failed to create user';
    } finally {
      creating = false;
    }
  }

  function startEdit(user: User) {
    editingId = user.id;
    editName = user.display_name;
    editUsername = user.username || '';
    editExternalId = user.external_id;
  }

  function cancelEdit() {
    editingId = null;
  }

  async function saveEdit() {
    if (editingId == null) return;
    if (editUsername && !/^[a-z][a-z0-9_]*[a-z0-9]$/.test(editUsername)) return;
    saving = true;
    try {
      const data: any = { display_name: editName.trim(), external_id: editExternalId.trim() };
      if (editUsername.trim()) data.username = editUsername.trim();
      const updated = await editUser(editingId, data);
      users = users.map(u => u.id === editingId ? updated : u);
      editingId = null;
    } catch (e) {
      // ignore
    } finally {
      saving = false;
    }
  }

  async function handleDelete(user: User) {
    if (!confirm(`Delete user "${user.display_name}"?`)) return;
    try {
      await deleteUser(user.id);
      users = users.filter(u => u.id !== user.id);
    } catch (e) {
      // ignore
    }
  }

  loadUsers();
</script>

<div class="users-page">
  <div class="page-header">
    <h2>Users</h2>
    <div class="header-actions">
      {#if !showForm}
        <button class="add-btn" onclick={() => showForm = true}>+ Add User</button>
      {/if}
      <button class="back-btn" onclick={onclose}>Back</button>
    </div>
  </div>

  {#if showForm}
    <div class="create-form">
      <h3>New User</h3>
      <div class="form-row">
        <label>
          <span class="label-text">Username *</span>
          <input type="text" bind:value={newUsername} placeholder="a-z, min 3 chars" />
        </label>
        <label>
          <span class="label-text">Display Name *</span>
          <input type="text" bind:value={newName} placeholder="Full name"
            onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleCreate(); } }}
          />
        </label>
        <label>
          <span class="label-text">External ID *</span>
          <input type="text" bind:value={newExternalId} placeholder="email or agent-id" />
        </label>
      </div>
      {#if createError}
        <p class="form-error">{createError}</p>
      {/if}
      <div class="form-actions">
        <button class="btn-cancel" onclick={() => { showForm = false; createError = ''; }}>Cancel</button>
        <button class="btn-submit" onclick={handleCreate} disabled={creating}>
          {creating ? 'Creating...' : 'Create'}
        </button>
      </div>
    </div>
  {/if}

  {#if loading}
    <p class="center">Loading users...</p>
  {:else if error}
    <p class="center error">{error}</p>
  {:else}
    <table>
      <thead>
        <tr>
          <th class="col-name">Name</th>
          <th class="col-username">Username</th>
          <th class="col-ext">External ID</th>
          <th class="col-actions"></th>
        </tr>
      </thead>
      <tbody>
        {#each rootUsers as user (user.id)}
          {@render userRow(user, 0)}
        {/each}
        {#if users.length === 0}
          <tr><td colspan="4" class="center">No users yet.</td></tr>
        {/if}
      </tbody>
    </table>
  {/if}
</div>

{#snippet userRow(user: User, depth: number)}
  {#if editingId === user.id}
    <tr class="editing">
      <td><input type="text" bind:value={editName} class="edit-input" /></td>
      <td><input type="text" bind:value={editUsername} class="edit-input mono" placeholder="a-z, min 3" /></td>
      <td><input type="text" bind:value={editExternalId} class="edit-input mono" /></td>
      <td class="col-actions">
        <button class="btn-save" onclick={saveEdit} disabled={saving}>Save</button>
        <button class="btn-cancel-sm" onclick={cancelEdit}>Cancel</button>
      </td>
    </tr>
  {:else}
    <tr>
      <td>
        <div class="name-cell" style="padding-left: {depth * 20}px">
          {#if hasChildren(user.id)}
            <button class="toggle-btn" onclick={() => toggleCollapse(user.id)}>
              <span class="chevron" class:collapsed={collapsed.has(user.id)}>&#9662;</span>
            </button>
          {:else if depth > 0}
            <span class="indent-spacer"></span>
          {/if}
          <span class="display-name">{user.display_name}</span>
        </div>
      </td>
      <td class="username">{user.username || '-'}</td>
      <td class="ext-id">{user.external_id}</td>
      <td class="col-actions">
        <button class="btn-edit" onclick={() => startEdit(user)}>Edit</button>
        <button class="btn-delete" onclick={() => handleDelete(user)}>Delete</button>
      </td>
    </tr>
  {/if}

  {#if hasChildren(user.id) && !collapsed.has(user.id)}
    {#each getChildren(user.id) as child (child.id)}
      {@render userRow(child, depth + 1)}
    {/each}
  {/if}
{/snippet}

<style>
  .users-page {
    padding: 16px 24px;
  }
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }
  .header-actions {
    display: flex;
    gap: 8px;
  }
  h2 {
    font-size: 20px;
    font-weight: 700;
  }
  .back-btn {
    background: var(--color-bg);
    color: var(--color-text-secondary);
    padding: 6px 14px;
    font-size: 13px;
  }
  .add-btn {
    background: var(--color-primary);
    color: white;
    font-weight: 600;
    padding: 6px 14px;
    font-size: 13px;
  }

  /* Create form */
  .create-form {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    padding: 16px;
    margin-bottom: 16px;
  }
  .create-form h3 {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 12px;
  }
  .form-row {
    display: flex;
    gap: 12px;
  }
  .form-row label {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .label-text {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--color-text-secondary);
  }
  .form-error {
    color: var(--importance-high);
    font-size: 13px;
    margin-top: 8px;
  }
  .form-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 12px;
  }
  .btn-cancel {
    background: var(--color-bg);
    color: var(--color-text);
    padding: 5px 14px;
    font-size: 13px;
  }
  .btn-submit {
    background: var(--color-primary);
    color: white;
    padding: 5px 14px;
    font-size: 13px;
    font-weight: 600;
  }
  .btn-submit:disabled {
    opacity: 0.5;
  }

  /* Table */
  table {
    width: 100%;
    border-collapse: collapse;
    background: var(--color-surface);
    border-radius: var(--radius);
    overflow: hidden;
    border: 1px solid var(--color-border);
  }
  th {
    text-align: left;
    padding: 10px 14px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    color: var(--color-text-secondary);
    border-bottom: 2px solid var(--color-border);
    background: var(--color-bg);
  }
  td {
    padding: 8px 14px;
    border-bottom: 1px solid var(--color-border);
    font-size: 13px;
    vertical-align: middle;
  }
  tr:last-child td {
    border-bottom: none;
  }
  .col-name {
    width: 30%;
  }
  .col-username {
    width: 25%;
  }
  .col-ext {
    width: 30%;
  }
  .col-actions {
    width: 15%;
    text-align: right;
    white-space: nowrap;
  }

  /* Name cell with tree */
  .name-cell {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .toggle-btn {
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    color: var(--color-text-secondary);
    font-size: 14px;
    width: 18px;
    height: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .toggle-btn:hover {
    color: var(--color-text);
  }
  .chevron {
    display: inline-block;
    transition: transform 0.15s;
  }
  .chevron.collapsed {
    transform: rotate(-90deg);
  }
  .indent-spacer {
    width: 18px;
    display: inline-block;
    flex-shrink: 0;
  }
  .display-name {
    font-weight: 500;
  }
  .username {
    font-family: monospace;
    font-size: 12px;
    color: var(--color-primary);
  }
  .ext-id {
    color: var(--color-text-secondary);
    font-family: monospace;
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 300px;
  }

  /* Row actions */
  .btn-edit, .btn-delete, .btn-save, .btn-cancel-sm {
    padding: 3px 8px;
    font-size: 12px;
    border-radius: 4px;
  }
  .btn-edit {
    background: var(--color-bg);
    color: var(--color-text);
  }
  .btn-delete {
    background: none;
    color: var(--status-cancelled);
    border: 1px solid var(--status-cancelled);
  }
  .btn-delete:hover {
    background: var(--status-cancelled);
    color: white;
  }
  .btn-save {
    background: var(--color-primary);
    color: white;
  }
  .btn-cancel-sm {
    background: var(--color-bg);
    color: var(--color-text);
  }

  /* Edit row */
  .editing td {
    padding: 6px 14px;
  }
  .edit-input {
    width: 100%;
    font-size: 12px;
    padding: 4px 6px;
    box-sizing: border-box;
  }
  .edit-input.mono {
    font-family: monospace;
  }

  .center {
    text-align: center;
    padding: 20px;
    color: var(--color-text-secondary);
  }
  .error {
    color: var(--importance-high);
  }

  @media (max-width: 768px) {
    .users-page {
      padding: 12px;
    }
    .form-row {
      flex-direction: column;
    }
    .col-ext {
      display: none;
    }
    th:nth-child(3), td:nth-child(3) {
      display: none;
    }
  }
</style>

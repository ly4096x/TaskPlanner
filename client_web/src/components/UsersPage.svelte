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

<div class="px-3 md:px-6 py-4">
  <div class="flex justify-between items-center mb-4">
    <h2 class="text-xl font-bold">Users</h2>
    <div class="flex gap-2">
      {#if !showForm}
        <button class="bg-primary text-white font-semibold py-1.5 px-3.5 text-[13px]" onclick={() => showForm = true}>+ Add User</button>
      {/if}
      <button class="bg-bg text-text-secondary py-1.5 px-3.5 text-[13px]" onclick={onclose}>Back</button>
    </div>
  </div>

  {#if showForm}
    <div class="bg-surface border border-border rounded-[--radius] p-4 mb-4">
      <h3 class="text-sm font-semibold mb-3">New User</h3>
      <div class="flex flex-col md:flex-row gap-3">
        <label class="flex-1 flex flex-col gap-1">
          <span class="text-[11px] font-semibold uppercase text-text-secondary">Username *</span>
          <input type="text" bind:value={newUsername} placeholder="a-z, min 3 chars" />
        </label>
        <label class="flex-1 flex flex-col gap-1">
          <span class="text-[11px] font-semibold uppercase text-text-secondary">Display Name *</span>
          <input type="text" bind:value={newName} placeholder="Full name"
            onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleCreate(); } }}
          />
        </label>
        <label class="flex-1 flex flex-col gap-1">
          <span class="text-[11px] font-semibold uppercase text-text-secondary">External ID *</span>
          <input type="text" bind:value={newExternalId} placeholder="email or agent-id" />
        </label>
      </div>
      {#if createError}
        <p class="text-[color:var(--importance-high)] text-[13px] mt-2">{createError}</p>
      {/if}
      <div class="flex gap-2 justify-end mt-3">
        <button class="bg-bg text-text py-[5px] px-3.5 text-[13px]" onclick={() => { showForm = false; createError = ''; }}>Cancel</button>
        <button class="bg-primary text-white py-[5px] px-3.5 text-[13px] font-semibold disabled:opacity-50" onclick={handleCreate} disabled={creating}>
          {creating ? 'Creating...' : 'Create'}
        </button>
      </div>
    </div>
  {/if}

  {#if loading}
    <p class="text-center py-5 text-text-secondary">Loading users...</p>
  {:else if error}
    <p class="text-center py-5 text-[color:var(--importance-high)]">{error}</p>
  {:else}
    <table class="w-full border-collapse bg-surface rounded-[--radius] overflow-hidden border border-border">
      <thead>
        <tr>
          <th class="text-left py-2.5 px-3.5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary border-b-2 border-border bg-bg w-[30%]">Name</th>
          <th class="text-left py-2.5 px-3.5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary border-b-2 border-border bg-bg w-[25%]">Username</th>
          <th class="text-left py-2.5 px-3.5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary border-b-2 border-border bg-bg w-[30%] hidden md:table-cell">External ID</th>
          <th class="text-right py-2.5 px-3.5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary border-b-2 border-border bg-bg w-[15%] whitespace-nowrap"></th>
        </tr>
      </thead>
      <tbody>
        {#each rootUsers as user (user.id)}
          {@render userRow(user, 0)}
        {/each}
        {#if users.length === 0}
          <tr><td colspan="4" class="text-center py-5 text-text-secondary">No users yet.</td></tr>
        {/if}
      </tbody>
    </table>
  {/if}
</div>

{#snippet userRow(user: User, depth: number)}
  {#if editingId === user.id}
    <tr>
      <td class="py-1.5 px-3.5 border-b border-border text-[13px] align-middle"><input type="text" bind:value={editName} class="w-full text-xs py-1 px-1.5 box-border" /></td>
      <td class="py-1.5 px-3.5 border-b border-border text-[13px] align-middle"><input type="text" bind:value={editUsername} class="w-full text-xs py-1 px-1.5 box-border font-mono" placeholder="a-z, min 3" /></td>
      <td class="py-1.5 px-3.5 border-b border-border text-[13px] align-middle hidden md:table-cell"><input type="text" bind:value={editExternalId} class="w-full text-xs py-1 px-1.5 box-border font-mono" /></td>
      <td class="py-1.5 px-3.5 border-b border-border text-[13px] align-middle text-right whitespace-nowrap">
        <button class="bg-primary text-white py-[3px] px-2 text-xs rounded disabled:opacity-50" onclick={saveEdit} disabled={saving}>Save</button>
        <button class="bg-bg text-text py-[3px] px-2 text-xs rounded" onclick={cancelEdit}>Cancel</button>
      </td>
    </tr>
  {:else}
    <tr>
      <td class="py-2 px-3.5 border-b border-border text-[13px] align-middle last:border-b-0">
        <div class="flex items-center gap-1" style="padding-left: {depth * 20}px">
          {#if hasChildren(user.id)}
            <button class="bg-none border-none p-0 cursor-pointer text-text-secondary text-sm w-[18px] h-[18px] inline-flex items-center justify-center shrink-0 hover:text-text" onclick={() => toggleCollapse(user.id)}>
              <span class="inline-block transition-transform duration-150 {collapsed.has(user.id) ? '-rotate-90' : ''}">&#9662;</span>
            </button>
          {:else if depth > 0}
            <span class="w-[18px] inline-block shrink-0"></span>
          {/if}
          <span class="font-medium">{user.display_name}</span>
        </div>
      </td>
      <td class="py-2 px-3.5 border-b border-border text-[13px] align-middle font-mono text-xs text-primary">{user.username || '-'}</td>
      <td class="py-2 px-3.5 border-b border-border text-[13px] align-middle text-text-secondary font-mono text-xs overflow-hidden text-ellipsis whitespace-nowrap max-w-[300px] hidden md:table-cell">{user.external_id}</td>
      <td class="py-2 px-3.5 border-b border-border text-[13px] align-middle text-right whitespace-nowrap">
        <button class="bg-bg text-text py-[3px] px-2 text-xs rounded" onclick={() => startEdit(user)}>Edit</button>
        <button class="bg-none text-[color:var(--status-cancelled)] border border-[color:var(--status-cancelled)] py-[3px] px-2 text-xs rounded hover:bg-[color:var(--status-cancelled)] hover:text-white" onclick={() => handleDelete(user)}>Delete</button>
      </td>
    </tr>
  {/if}

  {#if hasChildren(user.id) && !collapsed.has(user.id)}
    {#each getChildren(user.id) as child (child.id)}
      {@render userRow(child, depth + 1)}
    {/each}
  {/if}
{/snippet}

<script lang="ts">
  import { listUsers, createUser, editUser, createToken, listTokens, revokeToken, type User, type TokenInfo, type TokenCreated } from '../lib/api';
  import { Icon, ChevronDown } from 'svelte-hero-icons';

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
  let collapsed = $state<Set<number>>(new Set());

  // Token management
  let tokenUserId = $state<number | null>(null);
  let tokens = $state<TokenInfo[]>([]);
  let newTokenLabel = $state('');
  let createdToken = $state<string | null>(null);
  let tokenLoading = $state(false);

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
      createError = 'Username must be a-z, min 3 chars';
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

  async function handleSetRole(user: User, role: string) {
    try {
      const updated = await editUser(user.id, { role });
      users = users.map(u => u.id === updated.id ? updated : u);
    } catch {}
  }

  async function handleToggleDisabled(user: User) {
    try {
      const updated = await editUser(user.id, { disabled: user.disabled ? 0 : 1 });
      users = users.map(u => u.id === updated.id ? updated : u);
    } catch {}
  }

  async function showTokens(userId: number) {
    if (tokenUserId === userId) { tokenUserId = null; return; }
    tokenUserId = userId;
    createdToken = null;
    tokenLoading = true;
    try {
      tokens = await listTokens(userId);
    } catch { tokens = []; }
    finally { tokenLoading = false; }
  }

  async function handleCreateToken() {
    if (tokenUserId == null) return;
    try {
      const result = await createToken(tokenUserId, newTokenLabel.trim());
      createdToken = result.token;
      newTokenLabel = '';
      tokens = await listTokens(tokenUserId);
    } catch {}
  }

  async function handleRevokeToken(tokenId: number) {
    if (tokenUserId == null) return;
    try {
      await revokeToken(tokenUserId, tokenId);
      tokens = tokens.filter(t => t.id !== tokenId);
    } catch {}
  }

  function formatTime(ts: number): string {
    return new Date(ts * 1000).toLocaleString();
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
          <th class="text-left py-2.5 px-3.5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary border-b-2 border-border bg-bg">Name</th>
          <th class="text-left py-2.5 px-3.5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary border-b-2 border-border bg-bg hidden md:table-cell">External ID</th>
          <th class="text-left py-2.5 px-3.5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary border-b-2 border-border bg-bg w-[100px]">Role</th>
          <th class="text-right py-2.5 px-3.5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary border-b-2 border-border bg-bg w-[150px]"></th>
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
  <tr class="{user.disabled ? 'opacity-40' : ''}">
    <td class="py-2 px-3.5 border-b border-border text-[13px] align-middle">
      <div class="flex items-center gap-1" style="padding-left: {depth * 20}px">
        {#if hasChildren(user.id)}
          <!-- svelte-ignore a11y_consider_explicit_label -->
          <button class="bg-none border-none p-0 cursor-pointer text-text-secondary w-[18px] h-[18px] inline-flex items-center justify-center shrink-0 hover:text-text" onclick={() => toggleCollapse(user.id)}>
            <Icon src={ChevronDown} size="12" class="transition-transform duration-150 {collapsed.has(user.id) ? '-rotate-90' : ''}" />
          </button>
        {:else}
          <span class="w-[18px] inline-block shrink-0"></span>
        {/if}
        <span class="font-medium">{user.display_name}</span>
        <span class="text-xs text-primary font-mono ml-1">@{user.username}</span>
        {#if user.disabled}
          <span class="text-[10px] bg-[var(--importance-high)] text-white px-1.5 py-px rounded-full ml-1">disabled</span>
        {/if}
      </div>
    </td>
    <td class="py-2 px-3.5 border-b border-border text-[13px] align-middle text-text-secondary font-mono text-xs overflow-hidden text-ellipsis whitespace-nowrap max-w-[300px] hidden md:table-cell">{user.external_id}</td>
    <td class="py-2 px-3.5 border-b border-border text-[13px] align-middle">
      <select
        class="text-xs py-1 px-2 bg-bg border border-border rounded w-full"
        value={user.role || 'member'}
        onchange={(e) => handleSetRole(user, (e.target as HTMLSelectElement).value)}
      >
        <option value="admin">Admin</option>
        <option value="member">Member</option>
        <option value="viewer">Viewer</option>
      </select>
    </td>
    <td class="py-2 px-3.5 border-b border-border text-[13px] align-middle text-right whitespace-nowrap">
      <button class="bg-bg text-text py-[3px] px-2 text-xs rounded" onclick={() => showTokens(user.id)}>Tokens</button>
      <button
        class="text-text-secondary border border-border py-[3px] px-2 text-xs rounded hover:!bg-[var(--importance-high)] hover:!text-white hover:!border-[var(--importance-high)] {user.disabled ? '!border-[var(--status-new)] !text-[var(--status-new)]' : ''}"
        onclick={() => handleToggleDisabled(user)}
      >
        {user.disabled ? 'Enable' : 'Disable'}
      </button>
    </td>
  </tr>

  <!-- Token panel row -->
  {#if tokenUserId === user.id}
    <tr>
      <td colspan="4" class="px-3.5 py-3 border-b border-border bg-bg">
        <div style="padding-left: {depth * 20 + 18}px">
          <h4 class="text-xs font-semibold text-text-secondary uppercase mb-2">Access Tokens for {user.display_name}</h4>

          {#if createdToken}
            <div class="bg-[color-mix(in_srgb,var(--status-new)_10%,var(--color-surface))] border border-[var(--status-new)] rounded p-2 mb-2">
              <p class="text-xs text-text-secondary mb-1">New token (copy now — won't be shown again):</p>
              <code class="text-sm font-mono text-text select-all break-all">{createdToken}</code>
            </div>
          {/if}

          {#if tokenLoading}
            <p class="text-xs text-text-secondary">Loading...</p>
          {:else if tokens.length === 0}
            <p class="text-xs text-text-secondary mb-2">No tokens.</p>
          {:else}
            <div class="flex flex-col gap-1 mb-2">
              {#each tokens as t (t.id)}
                <div class="flex items-center justify-between text-xs bg-surface rounded px-2 py-1.5">
                  <div>
                    <span class="font-mono">#{t.id}</span>
                    {#if t.label}<span class="text-text-secondary ml-1">{t.label}</span>{/if}
                    <span class="text-text-secondary ml-2">last used: {t.last_used_time ? formatTime(t.last_used_time) : 'never'}</span>
                  </div>
                  <button class="text-text-secondary hover:!text-[var(--importance-high)] bg-none border-none text-xs px-1 cursor-pointer" onclick={() => handleRevokeToken(t.id)}>revoke</button>
                </div>
              {/each}
            </div>
          {/if}

          <div class="flex gap-2 items-center">
            <input type="text" bind:value={newTokenLabel} placeholder="Token label (optional)" class="text-xs py-1 px-2 flex-1" onkeydown={(e) => { if (e.key === 'Enter') handleCreateToken(); }} />
            <button class="bg-primary text-white text-xs py-1 px-3 font-semibold" onclick={handleCreateToken}>Create Token</button>
          </div>
        </div>
      </td>
    </tr>
  {/if}

  {#if hasChildren(user.id) && !collapsed.has(user.id)}
    {#each getChildren(user.id) as child (child.id)}
      {@render userRow(child, depth + 1)}
    {/each}
  {/if}
{/snippet}

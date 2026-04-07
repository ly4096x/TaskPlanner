<script lang="ts">
  import { listUsers, listBoards, createUser, editUser, createToken, listTokens, revokeToken, listRoles, createRoleApi, editRoleApi, deleteRoleApi, GLOBAL_ACL_ACTIONS, BOARD_ACL_ACTIONS, ACL_ACTIONS, type User, type TokenInfo, type TokenCreated, type Role, type Board } from '../lib/api';
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

  // Boards (for per-board permission editing)
  let allBoards = $state<Board[]>([]);

  // Roles
  let roles = $state<Role[]>([]);
  let showRoles = $state(false);
  let editingRoleId = $state<number | null>(null);
  let newRoleName = $state('');
  let newRoleDesc = $state('');
  let newRolePerms = $state<Set<string>>(new Set());
  let creatingRole = $state(false);

  async function loadRoles() {
    try { roles = await listRoles(); } catch { roles = []; }
    try { allBoards = await listBoards(true); } catch { allBoards = []; }
  }

  async function handleCreateRole() {
    if (!newRoleName.trim()) return;
    creatingRole = true;
    try {
      await createRoleApi({ name: newRoleName.trim(), description: newRoleDesc.trim(), permissions: [...newRolePerms] });
      newRoleName = '';
      newRoleDesc = '';
      newRolePerms = new Set();
      await loadRoles();
    } catch {} finally { creatingRole = false; }
  }

  async function handleDeleteRole(roleId: number) {
    try {
      await deleteRoleApi(roleId);
      await loadRoles();
    } catch {}
  }

  async function handleSaveRole(roleId: number, name: string, description: string, permissions: string[]) {
    try {
      await editRoleApi(roleId, { name, description, permissions });
      editingRoleId = null;
      await loadRoles();
    } catch {}
  }

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

  async function handleSetRole(user: User, roleId: string) {
    try {
      const updated = await editUser(user.id, { role_id: Number(roleId) } as any);
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
  loadRoles();
</script>

<div class="px-3 md:px-6 py-4">
  <div class="flex justify-between items-center mb-4">
    <h2 class="text-xl font-bold">Users</h2>
    <div class="flex gap-2">
      {#if !showForm}
        <button class="bg-primary text-white font-semibold py-1.5 px-3.5 text-[13px]" onclick={() => showForm = true}>+ Add User</button>
        <button class="bg-bg text-text-secondary py-1.5 px-3.5 text-[13px]" onclick={() => showRoles = !showRoles}>{showRoles ? 'Hide Roles' : 'Manage Roles'}</button>
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

  {#if showRoles}
    <div class="bg-surface border border-border rounded-[--radius] p-4 mb-4">
      <h3 class="text-sm font-semibold mb-3">Roles</h3>
      <div class="flex flex-col gap-2 mb-3">
        {#each roles as r (r.id)}
          <div class="flex items-center gap-3 py-1.5 px-2 bg-bg rounded text-sm">
            <span class="font-semibold min-w-[80px]">{r.name}</span>
            <span class="text-text-secondary text-xs flex-1">{r.permissions.join(', ') || '(none)'}</span>
            {#if r.built_in && r.name === 'admin'}<span class="text-[10px] text-text-secondary bg-border px-1.5 py-px rounded">built-in</span>
            {:else}
              <button class="text-xs text-text-secondary hover:text-text bg-none border-none cursor-pointer px-1" onclick={() => { editingRoleId = editingRoleId === r.id ? null : r.id; }}>edit</button>
            {/if}
            {#if !r.built_in}
              <button class="text-xs text-text-secondary hover:!text-[var(--importance-high)] bg-none border-none cursor-pointer px-1" onclick={() => handleDeleteRole(r.id)}>delete</button>
            {/if}
          </div>
          {#if editingRoleId === r.id && !(r.built_in && r.name === 'admin')}
            <div class="pl-4 py-2 border-l-2 border-primary">
              <!-- Default permissions (global + all-boards default) -->
              <h5 class="text-[11px] font-semibold uppercase text-text-secondary mb-1">Default permissions</h5>
              <div class="flex flex-wrap gap-3 mb-3">
                {#each ACL_ACTIONS as action}
                  <label class="flex items-center gap-1.5 text-xs cursor-pointer">
                    <input type="checkbox" checked={r.permissions.includes(action.id)} onchange={() => {
                      const perms = r.permissions.includes(action.id)
                        ? r.permissions.filter((p: string) => p !== action.id)
                        : [...r.permissions, action.id];
                      handleSaveRole(r.id, r.name, r.description, perms);
                    }} />
                    {action.label}
                  </label>
                {/each}
              </div>

              <!-- Per-board overrides matrix -->
              {#if allBoards.length > 0}
                <h5 class="text-[11px] font-semibold uppercase text-text-secondary mb-1">Per-board overrides <span class="font-normal normal-case">(overrides defaults for that board)</span></h5>
                <div class="overflow-x-auto">
                  <table class="text-xs border-collapse">
                    <thead>
                      <tr>
                        <th class="text-left py-1 px-2 text-text-secondary font-semibold">Board</th>
                        {#each BOARD_ACL_ACTIONS as action}
                          <th class="py-1 px-2 text-text-secondary font-semibold text-center whitespace-nowrap">{action.label}</th>
                        {/each}
                        <th class="py-1 px-2"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {#each allBoards as board (board.id)}
                        {@const bp = r.board_permissions.find((b: {board_id: number}) => b.board_id === board.id)}
                        <tr class="{bp ? 'bg-[color-mix(in_srgb,var(--color-primary)_5%,var(--color-bg))]' : ''}">
                          <td class="py-1 px-2 font-medium">{board.name}</td>
                          {#each BOARD_ACL_ACTIONS as action}
                            <td class="py-1 px-2 text-center">
                              {#if bp}
                                <input type="checkbox" checked={bp.actions.includes(action.id)} onchange={() => {
                                  const newActions = bp.actions.includes(action.id)
                                    ? bp.actions.filter((a: string) => a !== action.id)
                                    : [...bp.actions, action.id];
                                  const newBp = newActions.length > 0
                                    ? r.board_permissions.map((b: {board_id: number, actions: string[]}) => b.board_id === board.id ? {...b, actions: newActions} : b)
                                    : r.board_permissions.filter((b: {board_id: number}) => b.board_id !== board.id);
                                  editRoleApi(r.id, { board_permissions: newBp }).then(() => loadRoles());
                                }} />
                              {:else}
                                <input type="checkbox" checked={false} onchange={() => {
                                  const newBp = [...r.board_permissions, {board_id: board.id, actions: [action.id]}];
                                  editRoleApi(r.id, { board_permissions: newBp }).then(() => loadRoles());
                                }} />
                              {/if}
                            </td>
                          {/each}
                          <td class="py-1 px-2">
                            {#if bp}
                              <button class="text-[10px] text-text-secondary hover:text-text bg-none border-none cursor-pointer" onclick={() => {
                                const newBp = r.board_permissions.filter((b: {board_id: number}) => b.board_id !== board.id);
                                editRoleApi(r.id, { board_permissions: newBp }).then(() => loadRoles());
                              }}>clear</button>
                            {/if}
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              {/if}
            </div>
          {/if}
        {/each}
      </div>
      <div class="border-t border-border pt-3">
        <h4 class="text-xs font-semibold text-text-secondary uppercase mb-2">Create Role</h4>
        <div class="flex gap-2 items-end flex-wrap">
          <input type="text" bind:value={newRoleName} placeholder="Role name" class="text-xs py-1 px-2 w-32" />
          <input type="text" bind:value={newRoleDesc} placeholder="Description" class="text-xs py-1 px-2 flex-1" />
        </div>
        <div class="flex flex-wrap gap-3 mt-2 mb-2">
          {#each ACL_ACTIONS as action}
            <label class="flex items-center gap-1.5 text-xs cursor-pointer">
              <input type="checkbox" checked={newRolePerms.has(action.id)} onchange={() => {
                const next = new Set(newRolePerms);
                if (next.has(action.id)) next.delete(action.id); else next.add(action.id);
                newRolePerms = next;
              }} />
              {action.label}
            </label>
          {/each}
        </div>
        <button class="bg-primary text-white text-xs py-1 px-3 font-semibold disabled:opacity-50" onclick={handleCreateRole} disabled={creatingRole || !newRoleName.trim()}>
          {creatingRole ? 'Creating...' : 'Create Role'}
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
        value={user.role_id ?? ''}
        onchange={(e) => handleSetRole(user, (e.target as HTMLSelectElement).value)}
      >
        {#each roles as r (r.id)}
          <option value={r.id}>{r.name}</option>
        {/each}
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

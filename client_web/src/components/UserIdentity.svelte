<script lang="ts">
  import { listUsers, type User } from '../lib/api';

  interface Props {
    selected: User | null;
    onchange: (user: User | null) => void;
  }

  let { selected, onchange }: Props = $props();

  let users: User[] = $state([]);
  let open = $state(false);

  async function loadUsers() {
    try {
      users = await listUsers();
    } catch {}
  }

  function select(user: User) {
    onchange(user);
    localStorage.setItem('currentUserId', String(user.id));
    open = false;
  }

  loadUsers();
</script>

<div class="relative">
  <button class="flex items-center gap-1.5 bg-bg px-2.5 py-1 border border-border text-[13px] text-text rounded-[--radius] hover:border-text-secondary" onclick={() => { open = !open; if (open && users.length === 0) loadUsers(); }}>
    {#if selected}
      <span class="w-[22px] h-[22px] rounded-full bg-primary text-white text-xs font-semibold flex items-center justify-center">{selected.display_name.charAt(0).toUpperCase()}</span>
      <span class="max-w-[100px] overflow-hidden text-ellipsis whitespace-nowrap">{selected.display_name}</span>
    {:else}
      <span class="w-[22px] h-[22px] rounded-full bg-text-secondary text-white text-sm flex items-center justify-center">&#9787;</span>
      <span class="max-w-[100px] overflow-hidden text-ellipsis whitespace-nowrap">Select identity</span>
    {/if}
    <span class="text-[9px] text-text-secondary">{open ? '\u25B2' : '\u25BC'}</span>
  </button>

  {#if open}
    <div class="absolute top-full right-0 min-w-[200px] bg-surface border border-border rounded-[--radius] shadow-[0_4px_16px_rgba(0,0,0,0.15)] z-50 mt-1 max-h-[300px] overflow-y-auto">
      {#each users as user (user.id)}
        <button
          class="flex items-center gap-2 w-full text-left py-2 px-3 bg-none border-none rounded-none cursor-pointer hover:bg-bg {selected?.id === user.id ? 'bg-bg font-semibold' : ''}"
          onclick={() => select(user)}
        >
          <span class="w-7 h-7 rounded-full bg-primary text-white text-[13px] font-semibold flex items-center justify-center shrink-0">{user.display_name.charAt(0).toUpperCase()}</span>
          <span class="flex flex-col">
            <span class="text-[13px] text-text">{user.display_name}</span>
            <span class="text-[11px] text-text-secondary">@{user.username}</span>
          </span>
        </button>
      {/each}
    </div>
  {/if}
</div>

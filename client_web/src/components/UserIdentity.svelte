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

<div class="identity">
  <button class="identity-btn" onclick={() => { open = !open; if (open && users.length === 0) loadUsers(); }}>
    {#if selected}
      <span class="avatar">{selected.display_name.charAt(0).toUpperCase()}</span>
      <span class="name">{selected.display_name}</span>
    {:else}
      <span class="avatar no-user">&#9787;</span>
      <span class="name">Select identity</span>
    {/if}
    <span class="caret">{open ? '▲' : '▼'}</span>
  </button>

  {#if open}
    <div class="dropdown">
      {#each users as user (user.id)}
        <button
          class="user-item"
          class:active={selected?.id === user.id}
          onclick={() => select(user)}
        >
          <span class="item-avatar">{user.display_name.charAt(0).toUpperCase()}</span>
          <span class="item-info">
            <span class="item-name">{user.display_name}</span>
            <span class="item-username">@{user.username}</span>
          </span>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .identity {
    position: relative;
  }
  .identity-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    background: var(--color-bg);
    padding: 4px 10px;
    border: 1px solid var(--color-border);
    font-size: 13px;
    color: var(--color-text);
  }
  .identity-btn:hover {
    border-color: var(--color-text-secondary);
  }
  .avatar {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--color-primary);
    color: white;
    font-size: 12px;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .avatar.no-user {
    background: var(--color-text-secondary);
    font-size: 14px;
  }
  .name {
    max-width: 100px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .caret {
    font-size: 9px;
    color: var(--color-text-secondary);
  }
  .dropdown {
    position: absolute;
    top: 100%;
    right: 0;
    min-width: 200px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    box-shadow: 0 4px 16px rgba(0,0,0,0.15);
    z-index: 50;
    margin-top: 4px;
    max-height: 300px;
    overflow-y: auto;
  }
  .user-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    text-align: left;
    padding: 8px 12px;
    background: none;
    border: none;
    border-radius: 0;
    cursor: pointer;
  }
  .user-item:hover {
    background: var(--color-bg);
  }
  .user-item.active {
    background: var(--color-bg);
    font-weight: 600;
  }
  .item-avatar {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--color-primary);
    color: white;
    font-size: 13px;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .item-info {
    display: flex;
    flex-direction: column;
  }
  .item-name {
    font-size: 13px;
    color: var(--color-text);
  }
  .item-username {
    font-size: 11px;
    color: var(--color-text-secondary);
  }
</style>

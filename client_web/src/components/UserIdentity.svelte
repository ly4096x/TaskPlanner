<script lang="ts">
  import { getMe, setAccessToken, getAccessToken, type User } from '../lib/api';

  interface Props {
    selected: User | null;
    onchange: (user: User | null) => void;
  }

  let { selected, onchange }: Props = $props();

  let open = $state(false);
  let tokenInput = $state('');
  let error = $state('');
  let loading = $state(false);

  async function tryAuth() {
    const token = tokenInput.trim();
    if (!token) { error = 'Token required'; return; }
    error = '';
    loading = true;
    try {
      setAccessToken(token);
      const user = await getMe();
      onchange(user);
      tokenInput = '';
      open = false;
    } catch (e) {
      setAccessToken(null);
      error = 'Invalid or expired token';
    } finally {
      loading = false;
    }
  }

  function logout() {
    setAccessToken(null);
    onchange(null);
    open = false;
  }

  // Auto-login from stored token
  async function autoLogin() {
    const token = getAccessToken();
    if (token) {
      try {
        const user = await getMe();
        onchange(user);
      } catch {
        setAccessToken(null);
      }
    }
  }
  autoLogin();
</script>

<div class="relative">
  <button class="flex items-center gap-1.5 bg-bg px-2.5 py-1 border border-border text-[13px] text-text rounded-[--radius] hover:border-text-secondary" onclick={() => open = !open}>
    {#if selected}
      <span class="w-[22px] h-[22px] rounded-full bg-primary text-white text-xs font-semibold flex items-center justify-center">{selected.display_name.charAt(0).toUpperCase()}</span>
      <span class="max-w-[100px] overflow-hidden text-ellipsis whitespace-nowrap">{selected.display_name}</span>
    {:else}
      <span class="max-w-[100px] overflow-hidden text-ellipsis whitespace-nowrap text-text-secondary">Login</span>
    {/if}
    <span class="text-[9px] text-text-secondary">{open ? '\u25B2' : '\u25BC'}</span>
  </button>

  {#if open}
    <div class="absolute top-full right-0 min-w-[280px] bg-surface border border-border rounded-[--radius] shadow-[0_4px_16px_rgba(0,0,0,0.15)] z-50 mt-1 p-3">
      {#if selected}
        <div class="flex items-center gap-2 mb-3">
          <span class="w-8 h-8 rounded-full bg-primary text-white text-sm font-semibold flex items-center justify-center shrink-0">{selected.display_name.charAt(0).toUpperCase()}</span>
          <div class="flex flex-col">
            <span class="text-sm font-medium">{selected.display_name}</span>
            <span class="text-xs text-text-secondary">@{selected.username} &middot; {selected.role || 'member'}</span>
          </div>
        </div>
        <button class="w-full text-left py-1.5 px-2 bg-bg text-text-secondary text-xs rounded hover:text-text" onclick={logout}>
          Logout
        </button>
      {:else}
        <div class="flex flex-col gap-2">
          <label class="text-xs text-text-secondary font-semibold">Access Token</label>
          <input
            type="password"
            bind:value={tokenInput}
            placeholder="tp_..."
            class="text-sm"
            onkeydown={(e) => { if (e.key === 'Enter') tryAuth(); }}
          />
          {#if error}
            <p class="text-xs text-[color:var(--importance-high)] m-0">{error}</p>
          {/if}
          <button
            class="bg-primary text-white text-sm py-1.5 font-semibold disabled:opacity-50"
            onclick={tryAuth}
            disabled={loading}
          >
            {loading ? 'Verifying...' : 'Login'}
          </button>
        </div>
      {/if}
    </div>
  {/if}
</div>

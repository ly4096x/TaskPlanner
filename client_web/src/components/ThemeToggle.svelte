<script lang="ts">
  type Theme = 'light' | 'dark' | 'auto';

  let theme: Theme = $state(
    (localStorage.getItem('theme') as Theme) || 'auto'
  );

  function getSystemDark(): boolean {
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  function applyTheme(t: Theme) {
    const isDark = t === 'dark' || (t === 'auto' && getSystemDark());
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  }

  function setTheme(t: Theme) {
    theme = t;
    localStorage.setItem('theme', t);
    applyTheme(t);
  }

  const OPTIONS: { value: Theme; icon: string; label: string }[] = [
    { value: 'light', icon: '☀', label: 'Light' },
    { value: 'auto', icon: 'A', label: 'Auto' },
    { value: 'dark', icon: '☾', label: 'Dark' },
  ];

  // Apply on mount and whenever theme changes
  $effect(() => {
    applyTheme(theme);
  });

  // Listen for system theme changes when in auto mode
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (theme === 'auto') applyTheme('auto');
  });
</script>

<div class="theme-switch">
  {#each OPTIONS as opt}
    <button
      class="theme-opt"
      class:active={theme === opt.value}
      onclick={() => setTheme(opt.value)}
      title={opt.label}
    >
      <span class="icon">{opt.icon}</span>
    </button>
  {/each}
</div>

<style>
  .theme-switch {
    display: flex;
    border: 1px solid var(--color-border);
    border-radius: 6px;
    overflow: hidden;
  }
  .theme-opt {
    background: transparent;
    color: var(--color-text-secondary);
    border: none;
    padding: 4px 8px;
    font-size: 14px;
    cursor: pointer;
    display: flex;
    align-items: center;
    line-height: 1;
  }
  .theme-opt:hover {
    color: var(--color-text);
    background: var(--color-bg);
  }
  .theme-opt.active {
    background: var(--color-primary);
    color: white;
  }
  .theme-opt + .theme-opt {
    border-left: 1px solid var(--color-border);
  }
</style>

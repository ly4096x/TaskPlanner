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

<div class="flex border border-border rounded-md overflow-hidden">
  {#each OPTIONS as opt, i}
    <button
      class="border-none px-2 py-1 text-sm cursor-pointer flex items-center leading-none rounded-none {theme === opt.value ? '!bg-primary !text-white' : 'bg-transparent text-text-secondary hover:text-text hover:bg-bg'} {i > 0 ? 'border-l border-border' : ''}"
      onclick={() => setTheme(opt.value)}
      title={opt.label}
    >
      <span>{opt.icon}</span>
    </button>
  {/each}
</div>

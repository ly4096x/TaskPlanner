<script lang="ts">
  interface Props {
    view: 'list' | 'card';
    onchange: (view: 'list' | 'card') => void;
  }

  let { view, onchange }: Props = $props();
</script>

<div class="view-toggle">
  <button
    class:active={view === 'list'}
    onclick={() => onchange('list')}
    aria-label="List view"
  >
    <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor">
      <rect x="1" y="2" width="16" height="2" rx="1"/>
      <rect x="1" y="8" width="16" height="2" rx="1"/>
      <rect x="1" y="14" width="16" height="2" rx="1"/>
    </svg>
  </button>
  <button
    class:active={view === 'card'}
    onclick={() => onchange('card')}
    aria-label="Card view"
  >
    <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor">
      <rect x="1" y="1" width="7" height="7" rx="1"/>
      <rect x="10" y="1" width="7" height="7" rx="1"/>
      <rect x="1" y="10" width="7" height="7" rx="1"/>
      <rect x="10" y="10" width="7" height="7" rx="1"/>
    </svg>
  </button>
</div>

<style>
  .view-toggle {
    display: flex;
    gap: 4px;
    background: var(--color-border);
    border-radius: var(--radius);
    padding: 2px;
  }
  button {
    background: transparent;
    color: var(--color-text-secondary);
    padding: 6px 10px;
    display: flex;
    align-items: center;
  }
  button.active {
    background: var(--color-surface);
    color: var(--color-primary);
    box-shadow: var(--shadow);
  }
</style>

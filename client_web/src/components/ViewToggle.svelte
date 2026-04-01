<script lang="ts">
  interface Props {
    view: 'list' | 'card';
    onchange: (view: 'list' | 'card') => void;
  }

  let { view, onchange }: Props = $props();
</script>

<div class="flex gap-1 bg-border rounded-[--radius] p-0.5">
  <button
    class="py-1.5 px-2.5 flex items-center {view === 'list' ? '!bg-surface !text-primary shadow-[--shadow]' : 'bg-transparent text-text-secondary'}"
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
    class="py-1.5 px-2.5 flex items-center {view === 'card' ? '!bg-surface !text-primary shadow-[--shadow]' : 'bg-transparent text-text-secondary'}"
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

<script lang="ts">
  import { Icon, Bars3, Squares2x2 } from 'svelte-hero-icons';

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
    <Icon src={Bars3} size="18" />
  </button>
  <button
    class="py-1.5 px-2.5 flex items-center {view === 'card' ? '!bg-surface !text-primary shadow-[--shadow]' : 'bg-transparent text-text-secondary'}"
    onclick={() => onchange('card')}
    aria-label="Card view"
  >
    <Icon src={Squares2x2} size="18" />
  </button>
</div>

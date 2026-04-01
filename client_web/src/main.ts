import { mount } from 'svelte';
import './app.css';
import App from './App.svelte';

// Convert title attributes to data-tooltip for instant CSS tooltips
document.addEventListener('mouseenter', (e) => {
  const el = e.target as HTMLElement;
  if (el.title) {
    el.dataset.tooltip = el.title;
    el.title = '';
  }
}, true);
document.addEventListener('mouseleave', (e) => {
  const el = e.target as HTMLElement;
  if (el.dataset.tooltip) {
    el.title = el.dataset.tooltip;
    delete el.dataset.tooltip;
  }
}, true);

const app = mount(App, { target: document.getElementById('app')! });

export default app;

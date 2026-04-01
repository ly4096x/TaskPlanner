import { mount } from 'svelte';
import './app.css';
import App from './App.svelte';

// Instant tooltips — suppress native title delay, show a positioned div instead
const tip = document.createElement('div');
tip.id = 'tooltip';
document.body.appendChild(tip);

document.addEventListener('mouseenter', (e) => {
  const el = e.target as HTMLElement;
  if (el.title) {
    el.dataset.tooltip = el.title;
    el.title = '';
  }
  if (el.dataset.tooltip) {
    tip.textContent = el.dataset.tooltip;
    // Make visible off-screen to measure
    tip.style.left = '-9999px';
    tip.style.top = '-9999px';
    tip.classList.add('visible');
    const rect = el.getBoundingClientRect();
    const tipW = tip.offsetWidth;
    const tipH = tip.offsetHeight;
    // Center horizontally, clamp to viewport
    let left = rect.left + rect.width / 2 - tipW / 2;
    left = Math.max(4, Math.min(left, window.innerWidth - tipW - 4));
    // Prefer above, fall back to below if clipped
    let top = rect.top - tipH - 4;
    if (top < 4) top = rect.bottom + 4;
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  }
}, true);
document.addEventListener('mouseleave', (e) => {
  const el = e.target as HTMLElement;
  if (el.dataset.tooltip) {
    el.title = el.dataset.tooltip;
    delete el.dataset.tooltip;
    tip.classList.remove('visible');
  }
}, true);

const app = mount(App, { target: document.getElementById('app')! });

export default app;

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
    // Prefer below, fall back to above if clipped
    let top = rect.bottom + 4;
    if (top + tipH > window.innerHeight - 4) top = rect.top - tipH - 4;
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

// Auto drag-drop test: activate with ?test_drag in URL
const _testDrag = new URLSearchParams(window.location.search).has('test_drag');
if (_testDrag) {
  setTimeout(() => {
    function simulateDrag(source: HTMLElement, target: HTMLElement) {
      const sourceRect = source.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();

      const dataTransfer = new DataTransfer();

      source.dispatchEvent(new DragEvent('dragstart', {
        bubbles: true, cancelable: true, dataTransfer,
        clientX: sourceRect.left + sourceRect.width / 2,
        clientY: sourceRect.top + sourceRect.height / 2,
      }));

      target.dispatchEvent(new DragEvent('dragover', {
        bubbles: true, cancelable: true, dataTransfer,
        clientX: targetRect.left + targetRect.width / 2,
        clientY: targetRect.top + targetRect.height / 2,
      }));

      target.dispatchEvent(new DragEvent('drop', {
        bubbles: true, cancelable: true, dataTransfer,
        clientX: targetRect.left + targetRect.width / 2,
        clientY: targetRect.top + targetRect.height / 2,
      }));

      source.dispatchEvent(new DragEvent('dragend', {
        bubbles: true, cancelable: true, dataTransfer,
      }));
    }

    // Find first draggable card and the second column
    const card = document.querySelector('[draggable="true"]') as HTMLElement | null;
    const columns = document.querySelectorAll('[data-status]');
    if (card && columns.length >= 2) {
      const sourceStatus = card.closest('[data-status]')?.getAttribute('data-status');
      // Find a different column to drop on
      const targetCol = Array.from(columns).find(c => c.getAttribute('data-status') !== sourceStatus) as HTMLElement | null;
      if (targetCol) {
        console.log(`[test_drag] dragging from ${sourceStatus} to ${targetCol.dataset.status}`);
        simulateDrag(card, targetCol);
        console.log('[test_drag] done');
      } else {
        console.error('[test_drag] no target column found');
      }
    } else {
      console.error('[test_drag] no draggable card or columns found. Ensure kanban view is active.');
    }
  }, 2000); // Wait for Svelte to render
}

export default app;

import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import yaml from '@modyfi/vite-plugin-yaml';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [tailwindcss(), yaml(), svelte()],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
});

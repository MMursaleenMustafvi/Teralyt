import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
import path from 'node:path';

// The map data lives in data/ (written by tools/make_data.py and tools/make_index.py). The development server serves it
// at /data/, and the production build copies it into dist/data/, next to the page.
function mapData() {
  const dir = path.resolve('data');
  const type = f => (f.endsWith('.json') || f.endsWith('.geojson') ? 'application/json' : 'application/octet-stream');
  return {
    name: 'terralyt-map-data',
    configureServer(server) {
      server.middlewares.use('/data', (req, res, next) => {
        const f = path.join(dir, decodeURIComponent((req.url || '').split('?')[0]));
        if (!f.startsWith(dir) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) return next();
        res.setHeader('Content-Type', type(f)); res.setHeader('Cache-Control', 'no-cache');
        fs.createReadStream(f).pipe(res);
      });
    },
    closeBundle() { if (fs.existsSync('dist')) fs.cpSync(dir, path.resolve('dist/data'), { recursive: true }); }
  };
}

export default defineConfig({
  base: './',                       // the built site works from any folder (pages use hash routes: index.html#/map)
  plugins: [react(), mapData()],
  build: { chunkSizeWarningLimit: 1600, sourcemap: false },
  server: { port: 5173, open: false }
});

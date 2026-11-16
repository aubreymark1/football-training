import {defineConfig} from 'vite';
export default defineConfig({build:{outDir:'../static/chat',emptyOutDir:true,rollupOptions:{input:'main.jsx',output:{entryFileNames:'app.js',assetFileNames:'[name][extname]'}}}});

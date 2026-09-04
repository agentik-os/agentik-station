import { defineConfig } from "vite";

export default defineConfig({
  build: {
    emptyOutDir: true,
    minify: false,
    outDir: "server-dist",
    sourcemap: true,
    ssr: "server/server.ts",
    target: "node22",
    rollupOptions: {
      output: {
        entryFileNames: "server.js",
      },
    },
  },
});

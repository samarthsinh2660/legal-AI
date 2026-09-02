import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/** No @vitejs/plugin-react: it pulls a Babel 8 peer that conflicts with
 *  the Babel 7 already in the tree. Vitest 4 transforms JSX through oxc
 *  on its own, which is all these tests need. */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});

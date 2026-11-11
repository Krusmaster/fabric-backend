// Krusgraph: unit tests for the Model item's pure modules (definition load/save, versions). `npm test`.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["app/**/*.test.ts", "app/**/*.test.tsx"],
    environment: "node",
  },
});

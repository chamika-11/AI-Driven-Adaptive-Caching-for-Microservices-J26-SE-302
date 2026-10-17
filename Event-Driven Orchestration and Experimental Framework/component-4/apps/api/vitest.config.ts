import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@component4/shared": path.resolve(__dirname, "../../packages/shared/src/index.ts"),
    },
  },
});

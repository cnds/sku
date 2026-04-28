import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";

process.env.VITE_CJS_IGNORE_WARNING ??= "true";

export default defineConfig(async () => {
  const { vitePlugin: remix } = await import("@remix-run/dev");
  const future = {
    v3_fetcherPersist: true,
    v3_lazyRouteDiscovery: true,
    v3_relativeSplatPath: true,
    v3_singleFetch: true,
    v3_throwAbortReason: true,
  } as const;

  return {
    plugins: [react(), remix({ future }), tsconfigPaths()],
    server: {
      port: 3000,
    },
  };
});

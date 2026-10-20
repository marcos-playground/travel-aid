import type { NextConfig } from "next";

// On Vercel, vercel.json routes /api/* to the FastAPI service before Next.js sees it,
// so the proxy is only needed locally (or when API_URL is set explicitly).
const apiUrl = process.env.API_URL ?? (process.env.VERCEL ? undefined : "http://127.0.0.1:8000");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  reactCompiler: true,
  transpilePackages: ["@travel-aid/api-client"],
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // Keep the backend same-origin for the browser: /api/* is served by FastAPI.
  async rewrites() {
    return apiUrl ? [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }] : [];
  },
};

export default nextConfig;

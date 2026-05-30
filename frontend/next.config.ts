import type { NextConfig } from "next";

// BACKEND_URL is consumed at BUILD time by Next.js rewrites (baked into the
// routes manifest). For Code Engine deploys, the frontend image is built
// inside Code Engine's buildrun, so the deployed backend URL is the safe
// default. Locally, `BACKEND_URL=http://localhost:8000 npm run dev` overrides.
const BACKEND_URL =
  process.env.BACKEND_URL ??
  "https://backend.29vrap7vinsk.us-south.codeengine.appdomain.cloud";

const config: NextConfig = {
  reactStrictMode: true,
  // `output: 'standalone'` makes Next.js emit a self-contained server.js
  // bundle under .next/standalone that includes only the production deps
  // it actually traced. Combined with the multi-stage Dockerfile, this
  // drops the runner image from ~242 MB (full node_modules + .next) to
  // ~80 MB, which keeps us comfortably under IBM Container Registry's
  // 0.5 GB Lite-tier quota even after several deploys.
  output: "standalone",
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000",
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND_URL}/:path*` },
    ];
  },
};

export default config;

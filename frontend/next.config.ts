import type { NextConfig } from "next";

// The backend address is required: failing here beats proxying to a wrong default (CLAUDE.md Module 4).
// Rewrites are fixed at build time, so the same value must be present when the image is built.
const backend = process.env.BACKEND_INTERNAL_URL?.trim().replace(/\/+$/, "");
if (!backend || !/^https?:\/\//.test(backend)) {
  throw new Error("BACKEND_INTERNAL_URL must be set to the backend address, e.g. http://backend:8000");
}

const nextConfig: NextConfig = {
  output: "standalone",
  // Cache Components is off: every page here depends on the signed-in user's cookie and live
  // data, so there is nothing to cache and the extra rendering rules would only add friction.
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // The browser talks only to this app; these paths are forwarded to the backend so the session
  // cookie stays on one origin.
  async rewrites() {
    return [
      { source: "/auth/:path*", destination: `${backend}/auth/:path*` },
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
    ];
  },
};

export default nextConfig;

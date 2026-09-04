import type { NextConfig } from "next";

const apiBase = process.env.API_BASE_URL || "http://localhost:5001";
const apiProxyTimeoutMs = 120_000;

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  experimental: {
    // OCR-only queries can take longer than Next's 30-second rewrite default.
    proxyTimeout: apiProxyTimeoutMs,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

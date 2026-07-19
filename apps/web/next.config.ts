import type { NextConfig } from "next";

const apiBase = process.env.API_BASE_URL || "http://localhost:5001";

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
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

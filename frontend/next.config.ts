import path from "path";
import type { NextConfig } from "next";

const backendBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.join(__dirname),
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      {
        source: "/control/api/robots/:robotId/slam/map.png",
        destination: `${backendBase}/control/api/robots/:robotId/slam/map.png`,
      },
      {
        source: "/control/:path*",
        destination: `${backendBase}/control/:path*/`,
      },
    ];
  },
};

export default nextConfig;

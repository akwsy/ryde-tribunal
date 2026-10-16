import type { NextConfig } from "next";
const upstream = process.env.INTERNAL_API_ORIGIN?.replace(/\/$/, "");
const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return upstream ? [{ source: "/api/v1/:path*", destination: `${upstream}/api/v1/:path*` }] : [];
  },
};
export default nextConfig;

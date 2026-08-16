/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // keep FastAPI/rag/ingestion/gateways off the public network — proxy through Next
    const apiUrl = process.env.API_INTERNAL_URL || "http://api:8000";
    const waUrl = process.env.WA_GATEWAY_INTERNAL_URL || "http://wa-gateway:8100";
    const igUrl = process.env.IG_GATEWAY_INTERNAL_URL || "http://ig-gateway:8200";
    const ragUrl = process.env.RAG_INTERNAL_URL || "http://rag:8002";
    const ingestionUrl = process.env.INGESTION_INTERNAL_URL || "http://ingestion:8001";
    return [
      { source: "/api/back/:path*", destination: `${apiUrl}/:path*` },
      { source: "/api/wa/:path*", destination: `${waUrl}/:path*` },
      { source: "/api/ig/:path*", destination: `${igUrl}/:path*` },
      { source: "/api/rag/:path*", destination: `${ragUrl}/:path*` },
      { source: "/api/ingest/:path*", destination: `${ingestionUrl}/:path*` },
    ];
  },
};

export default nextConfig;
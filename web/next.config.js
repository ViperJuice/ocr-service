/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: 'http://localhost:8000/api/v1/:path*',
      },
      {
        source: '/api/monitoring/:path*',
        destination: 'http://localhost:8000/api/monitoring/:path*',
      },
    ];
  },
  // Turbopack configuration (Next.js 16+ default)
  turbopack: {},
  // Server component externals - prevent bundling of native modules
  serverExternalPackages: ['@boundaryml/baml', '@boundaryml/baml-linux-x64-gnu'],
};

module.exports = nextConfig;

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  images: {
    remotePatterns: [
      { hostname: "mc-heads.net" },
      { hostname: "minecraft.wiki" },
    ],
  },
}

export default nextConfig

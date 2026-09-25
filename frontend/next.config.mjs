/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      { hostname: "mc-heads.net" },
      { hostname: "minecraft.wiki" },
    ],
  },
}

export default nextConfig

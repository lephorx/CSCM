import { Geist, Geist_Mono, Montserrat } from "next/font/google"

import "./globals.css"
import { Toaster } from "@/components/ui/sonner"
import { cn } from "@/lib/utils"

const montserrat = Montserrat({ subsets: ["latin"], variable: "--font-sans" })

const fontMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
})

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      className={cn(
        "dark antialiased",
        fontMono.variable,
        "font-sans",
        montserrat.variable
      )}
    >
      <body>
        {children}
        <Toaster position="bottom-right" />
      </body>
    </html>
  )
}

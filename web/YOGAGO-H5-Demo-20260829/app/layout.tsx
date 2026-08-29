import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "伽伽狗｜你的具身智能瑜伽搭子",
  description: "YOGAGO | Your Embodied AI Yoga Buddy · Make Yoga Time Ours.",
  openGraph: {
    title: "伽伽狗｜你的具身智能瑜伽搭子",
    description: "Make Yoga Time Ours. 陪你共享瑜伽小时光",
    images: [{ url: "/og-yogago.jpg", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "YOGAGO | Your Embodied AI Yoga Buddy",
    description: "Make Yoga Time Ours. 陪你共享瑜伽小时光",
    images: ["/og-yogago.jpg"],
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}

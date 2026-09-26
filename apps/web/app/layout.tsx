import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

const plexSans = IBM_Plex_Sans({ variable: "--font-plex-sans", subsets: ["latin"], weight: ["400", "500", "600"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500", "600"] });

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL; // set in production (e.g. https://<project>.vercel.app); absolute OG image URLs need it
const DESCRIPTION =
  "Independent research on bandwidth-constrained downlink using archived Curiosity Navcam data. On a held-out test (sols 950–979), " +
  "position-based traverse sampling with a stereo-safe progressive scheduler kept 1/4 of frames: 26.1% of full-quality bytes, " +
  "100% 5 m coverage, 0 broken stereo pairs.";

export const metadata: Metadata = {
  ...(SITE_URL ? { metadataBase: new URL(SITE_URL) } : {}),
  title: { default: "DEEPSIFT — Autonomous Downlink Research", template: "%s · DEEPSIFT" },
  description: DESCRIPTION,
  openGraph: { title: "DEEPSIFT — Autonomous Downlink Research", description: DESCRIPTION, type: "website", siteName: "DEEPSIFT" },
  twitter: { card: "summary_large_image", title: "DEEPSIFT — Autonomous Downlink Research", description: DESCRIPTION },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}

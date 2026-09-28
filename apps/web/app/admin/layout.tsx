import type { Metadata } from "next";

export const metadata: Metadata = { title: "Private", robots: { index: false, follow: false, nocache: true } };

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <div className="home min-h-screen">{children}</div>;
}

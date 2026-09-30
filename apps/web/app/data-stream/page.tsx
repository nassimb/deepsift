import type { Metadata } from "next";
import { ObservatoryClient } from "@/components/observatory/ObservatoryClient";
import { PageTopBar, ReleaseFooter } from "@/components/release/Shell";

export const metadata: Metadata = {
  title: "Live data observatory",
  description: "Real-time and near-real-time public signals across deep-space communications (DSN Now), Mars data publication and the space environment. Independent DEEPSIFT monitoring interface.",
};

export default function DataStreamPage() {
  return (
    <div className="home">
      <PageTopBar label="DATA STREAM" />
      <main className="max-w-[1480px] mx-auto px-3 sm:px-5 py-5">
        <ObservatoryClient />
      </main>
      <ReleaseFooter />
    </div>
  );
}

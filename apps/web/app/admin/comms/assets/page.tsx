import type { Metadata } from "next";
import { AssetsView } from "@/components/comms/views";

export const metadata: Metadata = { title: "Assets" };

export default function Page() {
  return <AssetsView />;
}

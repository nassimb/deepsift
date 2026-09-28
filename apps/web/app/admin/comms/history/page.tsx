import type { Metadata } from "next";
import { HistoryView } from "@/components/comms/views";

export const metadata: Metadata = { title: "History" };

export default function Page() {
  return <HistoryView />;
}

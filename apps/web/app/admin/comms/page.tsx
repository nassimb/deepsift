import type { Metadata } from "next";
import { TodayView } from "@/components/comms/views";

export const metadata: Metadata = { title: "Today" };

export default function Page() {
  return <TodayView />;
}

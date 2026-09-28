import type { Metadata } from "next";
import { ReviewView } from "@/components/comms/views";

export const metadata: Metadata = { title: "Weekly review" };

export default function Page() {
  return <ReviewView />;
}

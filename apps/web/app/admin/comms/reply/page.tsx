import type { Metadata } from "next";
import { ReplyLabView } from "@/components/comms/ReplyLab";

export const metadata: Metadata = { title: "Reply lab" };

export default function Page() {
  return <ReplyLabView />;
}

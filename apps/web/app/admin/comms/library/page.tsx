import type { Metadata } from "next";
import { LibraryView } from "@/components/comms/views";

export const metadata: Metadata = { title: "Library" };

export default function Page() {
  return <LibraryView />;
}

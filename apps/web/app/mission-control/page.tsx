import type { Metadata } from "next";
import { MissionControl } from "@/components/mission/MissionControl";

export const metadata: Metadata = {
  title: "Mission Control",
  description:
    "Historical replay of the held-out Curiosity Navcam traverses (sols 950–979): Scheduler V3 + rover-position sampling at 1/4 frame retention. Static, frozen release data.",
};

export default function MissionControlPage() {
  return <MissionControl />;
}

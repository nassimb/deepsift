import { ReleaseFooter, PageTopBar, Section } from "@/components/release/Shell";
import { REL } from "@/lib/release";

const ITEMS: [string, string][] = [
  ["PDS survivorship bias", "The Planetary Data System contains only observations the mission actually downlinked. DEEPSIFT cannot see images that were never sent or were deleted onboard, so every result is about re-prioritizing archived observations, not about the rover’s full onboard image stream."],
  ["Archived, downlinked observations only", "The replay treats archived products as if they were waiting onboard. It is a retrospective experiment; it does not reconstruct what the rover actually held in storage at any time."],
  ["Simulated compressed stereo tier", "Scheduler V3’s COMPRESSED_STEREO_PAIR is DEEPSIFT’s own JPEG q50 ground re-encoding of both eyes — a SIMULATED PRODUCT TIER, not a NASA flight product. Traverse results use only NASA label estimates (full-quality and thumbnail pairs)."],
  ["PLACES interpolation", "Rover positions come from the PLACES localized_interp table, matched by site/drive/pose; most frames use the nearest pose within their drive, not a per-frame onboard localization. Spatial metrics inherit that resolution."],
  ["One rover, one camera", "Curiosity Navcam only. Nothing here is tested on other cameras (Mastcam, Hazcam, ChemCam RMI), other rovers or orbiters."],
  ["Limited mission windows", `Four sol windows (412–430, 779–820, 1100–1129, 950–979) and traverse sequences only. Test: ${REL.test_dataset.traverse_sequences_ge_10_frames} traverses, ${REL.test_dataset.traverse_frames} frames.`],
  ["Visual-change proxy ≠ scientific value", "Visual-change coverage is a MobileNetV2 embedding similarity. It is not a judgement of scientific interest, and spatial coverage is geometric: neither metric measures whether science value was preserved."],
  ["No flight hardware test", "Everything ran on a laptop CPU. There is no test on radiation-tolerant flight processors, flight software frameworks or real storage hardware."],
  ["No power, thermal or compute-budget model", "The simulation models bytes, not energy, heat, CPU time or memory on a spacecraft."],
  ["No NASA validation", "DEEPSIFT is an independent research prototype. It is not reviewed, endorsed, used or validated by NASA, JPL or the MSL mission team."],
  ["Failed components are excluded, not fixed", "QUALITY_V2 (validation false-positive rate 10.6 % vs 3.6 % in development) and constrained pHash (false-merge 0.15–0.19) failed validation and are not part of the claim. A quality detector would need a new validation interval."],
  ["The held-out test is used up", "The final test interval has been analysed once. Any change to the method now needs a new, untouched test interval."],
];

export default function Limitations() {
  return (
    <div className="home">
      <PageTopBar label="LIMITATIONS" />
      <main>
        <Section kicker="Limitations" title="What the result does not show."
          lead="The held-out result is narrow on purpose. These limits travel with it; please read them before quoting any number.">
          <ol className="grid gap-3 md:grid-cols-2">
            {ITEMS.map(([t, d], i) => (
              <li key={t} className="panel p-4">
                <div className="flex items-baseline gap-2">
                  <span className="mono text-[10px] text-ink-4">{String(i + 1).padStart(2, "0")}</span>
                  <span className="text-[14px] text-ink">{t}</span>
                </div>
                <p className="text-[13px] text-ink-2 mt-1 leading-relaxed">{d}</p>
              </li>
            ))}
          </ol>
        </Section>
        <Section kicker="What the result does show" title="A narrow, reproducible statement.">
          <p className="text-[14px] text-ink-2 leading-relaxed max-w-3xl">
            On a held-out Curiosity Navcam interval (sols 950–979), position-based traverse sampling with a stereo-safe progressive scheduler kept 1/4 of
            traverse frames at full quality, using {(REL.headline.bytes_fraction * 100).toFixed(1)}% of full-quality traverse bytes, while every archived
            traverse frame stayed within 5 m of a kept frame (maximum {REL.headline.max_distance_to_kept_m_worst.toFixed(2)} m) and no stereo pair was broken.
          </p>
        </Section>
      </main>
      <ReleaseFooter />
    </div>
  );
}

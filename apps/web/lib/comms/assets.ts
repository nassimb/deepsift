/** Approved existing DEEPSIFT visuals for posts — read-only references, nothing is generated or modified.
 *  X only accepts raster images, so every image asset lists the exact PNG/JPEG file(s) to attach (`files`), never an SVG.
 *  /share/*.png are byte-identical copies of the frozen release PNGs (docs/figures, artifacts/public/media), checked by
 *  tests/comms-assets.test.ts. PDFs and pages to capture have no attachable file. */
import type { Pillar } from "./library.ts";

export type AssetKind = "FIGURE" | "SCREENSHOT" | "NAVCAM" | "PAGE" | "RECORDING" | "DOCUMENT";

export interface Asset {
  id: string;
  name: string;
  kind: AssetKind;
  description: string;
  /** Image shown in the console (null for things you still have to capture). */
  preview: string | null;
  /** Where OPEN goes. */
  open: string;
  /** Files to attach on X — PNG or JPEG only (empty for recordings, pages to capture and PDFs). */
  files: { url: string; format: "PNG" | "JPEG"; source: string }[];
  /** Repo path (or site path) for COPY PATH. */
  path: string;
  pillars: Pillar[];
  caption?: string;
}

const BLOB = "https://github.com/nassimb/deepsift/blob/main";
const NAV = "/navcam/SOL00967";
const NAV_L = `${NAV}/NLB_483332396EDR_D0470000TRAV00327M1.jpg`;
const NAV_R = `${NAV}/NRB_483332396EDR_D0470000TRAV00327M1.jpg`;
const png = (name: string, source: string) => [{ url: `/share/${name}`, format: "PNG" as const, source }];
const fig = (name: string) => png(`${name}.png`, `docs/figures/${name}.png`);
const media = (name: string) => png(`${name}.png`, `artifacts/public/media/${name}.png`);

export const ASSETS: Asset[] = [
  {
    id: "mc_recording", name: "Mission Control short recording", kind: "RECORDING",
    description: "15–25 s screen recording of /mission-control: SEND ALL → POSITION · 1/4 on the example traverse. Record it yourself (see the video idea on the post).",
    preview: null, files: [], open: "/mission-control", path: "https://deepsift.space/mission-control", pillars: ["MISSION_CONTROL"],
    caption: "Historical replay of archived Curiosity Navcam data (held-out test). Not a live feed.",
  },
  {
    id: "mc_screenshot", name: "Mission Control screenshot", kind: "PAGE",
    description: "Capture /mission-control in its FINAL STATE (POSITION · 1/4) with the KPI strip and a selected frame's decision reason visible.",
    preview: null, files: [], open: "/mission-control", path: "https://deepsift.space/mission-control", pillars: ["MISSION_CONTROL", "FINAL_RESULT"],
  },
  {
    id: "final_test_replay", name: "Final-test replay", kind: "SCREENSHOT",
    description: "/final-test historical replay of traverse 967:trav00327, POSITION at 1/4, fully shown (release media #2).",
    preview: "/share/02_final_test_replay_overview.png", files: media("02_final_test_replay_overview"), open: "/final-test",
    path: "artifacts/public/media/02_final_test_replay_overview.png", pillars: ["MISSION_CONTROL", "FINAL_RESULT"],
    caption: "Historical replay of a held-out Curiosity Navcam traverse. Filled squares are frames kept at full quality; everything else goes down as a thumbnail pair.",
  },
  {
    id: "media_headline", name: "Held-out result panel", kind: "SCREENSHOT",
    description: "Homepage hero with the held-out result KPIs (release media #1).",
    preview: "/share/01_homepage_final_result.png", files: media("01_homepage_final_result"), open: `${BLOB}/artifacts/public/media/01_homepage_final_result.png`,
    path: "artifacts/public/media/01_homepage_final_result.png", pillars: ["FINAL_RESULT"],
  },
  {
    id: "fig1", name: "Held-out test figure (bytes vs coverage)", kind: "FIGURE",
    description: "Figure 1: bytes vs 5 m coverage and vs largest distance to a kept frame at 1/8, 1/4, 1/2 — all frozen methods.",
    preview: "/share/fig1_bytes_vs_coverage.png", files: fig("fig1_bytes_vs_coverage"), open: "/share/fig1_bytes_vs_coverage.png", path: "docs/figures/fig1_bytes_vs_coverage.png",
    pillars: ["FINAL_RESULT", "ENGINEERING"],
  },
  {
    id: "fig2", name: "Four-period generalization figure", kind: "FIGURE",
    description: "Figure 2: POSITION at 1/4 in four non-pooled periods.",
    preview: "/share/fig2_four_period_generalization.png", files: fig("fig2_four_period_generalization"), open: "/share/fig2_four_period_generalization.png",
    path: "docs/figures/fig2_four_period_generalization.png", pillars: ["FINAL_RESULT", "METHODOLOGY"],
  },
  {
    id: "fig3", name: "Embedding negative-result chart", kind: "FIGURE",
    description: "Figure 3: embedding visual-change gain by period with 95% intervals and the +0.020 threshold.",
    preview: "/share/fig3_embedding_gain_by_period.png", files: fig("fig3_embedding_gain_by_period"), open: "/share/fig3_embedding_gain_by_period.png",
    path: "docs/figures/fig3_embedding_gain_by_period.png", pillars: ["NEGATIVE_RESULT", "BUILD_STORY"],
  },
  {
    id: "fig4", name: "Research funnel", kind: "FIGURE",
    description: "Figure 4: what survived the research funnel (verdicts from pre-registered rules).",
    preview: "/share/fig4_research_funnel.png", files: fig("fig4_research_funnel"), open: "/share/fig4_research_funnel.png", path: "docs/figures/fig4_research_funnel.png",
    pillars: ["NEGATIVE_RESULT", "BUILD_STORY", "METHODOLOGY"],
  },
  {
    id: "fig5", name: "Example traverse figure", kind: "FIGURE",
    description: "Figure 5: example held-out traverse 967:trav00327 (longest path; not claimed representative) — kept vs thumbnail-only frames, 5 m discs.",
    preview: "/share/fig5_example_traverse.png", files: fig("fig5_example_traverse"), open: "/share/fig5_example_traverse.png", path: "docs/figures/fig5_example_traverse.png",
    pillars: ["MISSION_CONTROL", "MARS_VISUAL", "ENGINEERING"],
  },
  {
    id: "media_survived", name: "What survived (site section)", kind: "SCREENSHOT",
    description: "'What didn't work' vs 'What generalized' (release media #5).",
    preview: "/share/05_what_survived.png", files: media("05_what_survived"), open: `${BLOB}/artifacts/public/media/05_what_survived.png`,
    path: "artifacts/public/media/05_what_survived.png", pillars: ["NEGATIVE_RESULT", "BUILD_STORY"],
  },
  {
    id: "media_four_period", name: "Four-period panel (site section)", kind: "SCREENSHOT",
    description: "Four-period small multiples plus the embedding-gain panel (release media #4).",
    preview: "/share/04_four_period_generalization.png", files: media("04_four_period_generalization"), open: `${BLOB}/artifacts/public/media/04_four_period_generalization.png`,
    path: "artifacts/public/media/04_four_period_generalization.png", pillars: ["FINAL_RESULT", "NEGATIVE_RESULT"],
  },
  {
    id: "navcam_left", name: "Navcam observation preview (sol 967, left eye)", kind: "NAVCAM",
    description: "Real archived Curiosity Navcam frame from the held-out traverse 967:trav00327. Contrast-stretched display preview; credit NASA/JPL-Caltech.",
    preview: NAV_L, files: [{ url: NAV_L, format: "JPEG", source: `apps/web/public${NAV_L}` }], open: NAV_L, path: `apps/web/public${NAV_L}`, pillars: ["MARS_VISUAL"],
    caption: "Curiosity Navcam, sol 967 (archived PDS product). Image: NASA/JPL-Caltech. Display preview, contrast-stretched.",
  },
  {
    id: "navcam_pair", name: "Navcam stereo pair (sol 967, left + right)", kind: "NAVCAM",
    description: "Both eyes of one archived stereo acquisition — attach the two images together. Credit NASA/JPL-Caltech.",
    preview: NAV_R, files: [{ url: NAV_L, format: "JPEG", source: `apps/web/public${NAV_L}` }, { url: NAV_R, format: "JPEG", source: `apps/web/public${NAV_R}` }], open: NAV_R, path: `apps/web/public${NAV_L} + apps/web/public${NAV_R}`, pillars: ["MARS_VISUAL", "ENGINEERING"],
    caption: "Left and right Navcam eyes of one acquisition, sol 967. Image: NASA/JPL-Caltech. Display previews, contrast-stretched.",
  },
  {
    id: "paper", name: "Paper (PDF)", kind: "DOCUMENT",
    description: "DEEPSIFT v1 paper — pre-registered retrospective study.",
    preview: null, files: [], open: `${BLOB}/artifacts/public/deepsift-v1-paper.pdf`, path: "artifacts/public/deepsift-v1-paper.pdf",
    pillars: ["METHODOLOGY", "REPRODUCIBILITY"],
  },
  {
    id: "one_pager", name: "One-pager (PDF)", kind: "DOCUMENT",
    description: "One-page summary of the result and limitations.",
    preview: null, files: [], open: `${BLOB}/artifacts/public/deepsift-one-pager.pdf`, path: "artifacts/public/deepsift-one-pager.pdf",
    pillars: ["FINAL_RESULT", "QUESTION"],
  },
  {
    id: "reproducibility_page", name: "Reproducibility page", kind: "PAGE",
    description: "Hashes, commits, tags and the frozen-before-download timeline. Screenshot the 'frozen before download' panel.",
    preview: null, files: [], open: "/reproducibility", path: "https://deepsift.space/reproducibility", pillars: ["REPRODUCIBILITY", "METHODOLOGY"],
  },
];

export const ASSET_BY_ID: Record<string, Asset> = Object.fromEntries(ASSETS.map((a) => [a.id, a]));

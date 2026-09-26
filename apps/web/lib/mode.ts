/** Public release mode (static deployment, e.g. Vercel): NEXT_PUBLIC_DEEPSIFT_PUBLIC_RELEASE=1.
 *  In this mode the site never contacts the local pipeline API (no localhost requests from visitors' browsers), local research
 *  tools are hidden from navigation (not deleted), and every research page reads frozen data from data/release.json. */
export const PUBLIC_RELEASE = process.env.NEXT_PUBLIC_DEEPSIFT_PUBLIC_RELEASE === "1";
export const API_CONFIGURED = Boolean(process.env.NEXT_PUBLIC_DEEPSIFT_API);
/** True when pages may call the pipeline API: always locally; in public mode only if an API URL was explicitly configured. */
export const API_ENABLED = !PUBLIC_RELEASE || API_CONFIGURED;

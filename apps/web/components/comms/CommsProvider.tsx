"use client";

/* Browser-local editorial state for the private console (localStorage only — see lib/comms/store.ts). */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Mode } from "@/lib/comms/library";
import { emptyState, loadState, saveState, upsert, type CommsState, type EditorialItem } from "@/lib/comms/store";

interface Ctx {
  state: CommsState;
  ready: boolean;
  saved: boolean;
  put: (it: EditorialItem) => void;
  replace: (s: CommsState) => void;
  mode: Mode;
  setMode: (m: Mode) => void;
}

const CommsCtx = createContext<Ctx | null>(null);
const MODE_KEY = "deepsift-comms-mode";

export function CommsProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<CommsState>(emptyState);
  const [ready, setReady] = useState(false);
  const [saved, setSaved] = useState(true);
  const [mode, setModeState] = useState<Mode>("ALL");

  // Browser storage can only be read after hydration (the server has no localStorage), hence the effect.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState(loadState());
    try {
      const m = window.localStorage.getItem(MODE_KEY);
      if (m === "ALL" || m === "RESEARCH" || m === "FAN") setModeState(m);
    } catch {}
    setReady(true);
  }, []);

  const commit = useCallback((next: CommsState) => {
    setState(next);
    setSaved(saveState(next));
  }, []);

  const put = useCallback((it: EditorialItem) => setState((s) => {
    const next = upsert(s, it);
    setSaved(saveState(next));
    return next;
  }), []);

  const setMode = useCallback((m: Mode) => {
    setModeState(m);
    try { window.localStorage.setItem(MODE_KEY, m); } catch {}
  }, []);

  const value = useMemo(() => ({ state, ready, saved, put, replace: commit, mode, setMode }), [state, ready, saved, put, commit, mode, setMode]);
  return <CommsCtx.Provider value={value}>{children}</CommsCtx.Provider>;
}

export function useComms(): Ctx {
  const c = useContext(CommsCtx);
  if (!c) throw new Error("useComms outside CommsProvider");
  return c;
}

/** Latest non-rejected item for an idea (or the latest one of any status). */
export function itemForIdea(state: CommsState, ideaId: string): EditorialItem | null {
  const mine = state.items.filter((i) => i.idea_id === ideaId).sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return mine.find((i) => i.status !== "REJECTED" && i.status !== "POSTED") ?? mine[0] ?? null;
}

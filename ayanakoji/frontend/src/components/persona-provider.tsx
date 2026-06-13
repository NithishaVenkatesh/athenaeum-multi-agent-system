"use client";

/**
 * Persona session. "Signing in" is choosing a learner persona — there are no
 * passwords. The selection is the session: it persists in localStorage and is
 * exposed app-wide so the chat workspace knows whose courses to load. Sign out
 * clears it.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import type { PersonaSummary } from "@/lib/api";

const STORAGE_KEY = "athenaeum.persona";

interface PersonaContextValue {
  persona: PersonaSummary | null;
  /** False until localStorage has been read (avoids redirecting before hydration). */
  ready: boolean;
  selectPersona: (persona: PersonaSummary) => void;
  signOut: () => void;
}

const PersonaContext = createContext<PersonaContextValue | null>(null);

function readStoredPersona(): PersonaSummary | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PersonaSummary) : null;
  } catch {
    return null; // Malformed storage — treat as signed out.
  }
}

export function PersonaProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<{
    persona: PersonaSummary | null;
    ready: boolean;
  }>({ persona: null, ready: false });

  useEffect(() => {
    // One-time hydration from localStorage after mount. Reading in a lazy
    // initializer would diverge from the server-rendered (null) markup, so the
    // read intentionally happens here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ persona: readStoredPersona(), ready: true });
  }, []);

  const selectPersona = useCallback((next: PersonaSummary) => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setState((prev) => ({ ...prev, persona: next }));
  }, []);

  const signOut = useCallback(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    setState((prev) => ({ ...prev, persona: null }));
  }, []);

  const value = useMemo(
    () => ({
      persona: state.persona,
      ready: state.ready,
      selectPersona,
      signOut,
    }),
    [state.persona, state.ready, selectPersona, signOut],
  );

  return (
    <PersonaContext.Provider value={value}>{children}</PersonaContext.Provider>
  );
}

export function usePersona(): PersonaContextValue {
  const context = useContext(PersonaContext);
  if (!context) {
    throw new Error("usePersona must be used within a PersonaProvider");
  }
  return context;
}

/**
 * VisionX Auth Session
 * Stores the backend-issued JWT session in localStorage and notifies listeners.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const STORAGE_KEY = "visionx.auth.session";

export interface User {
  id: string;
  email: string;
  created_at?: string;
  user_metadata: { full_name?: string | null };
}

export interface Session {
  access_token: string;
  refresh_token: string;
  expires_at: number; // unix seconds
  user: User;
}

type AuthEvent = "SIGNED_IN" | "SIGNED_OUT" | "TOKEN_REFRESHED";
type Listener = (event: AuthEvent, session: Session | null) => void;

const listeners = new Set<Listener>();
let refreshing: Promise<Session | null> | null = null;

function read(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

function write(session: Session | null) {
  if (typeof window === "undefined") return;
  try {
    if (session) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage unavailable (private mode); session lives in memory only for this page
  }
}

function emit(event: AuthEvent, session: Session | null) {
  listeners.forEach((cb) => cb(event, session));
}

function jwtExp(token: string): number {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.exp === "number" ? payload.exp : 0;
  } catch {
    return 0;
  }
}

async function fetchUser(accessToken: string): Promise<User | null> {
  const res = await fetch(`${API_URL}/api/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) return null;
  const body = await res.json();
  return body?.user ?? null;
}

async function setSession(tokens: { access_token: string; refresh_token: string }) {
  try {
    const user = await fetchUser(tokens.access_token);
    if (!user) return { data: { session: null }, error: new Error("Invalid session") };
    const session: Session = {
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
      expires_at: jwtExp(tokens.access_token),
      user,
    };
    const hadSession = Boolean(read());
    write(session);
    emit(hadSession ? "TOKEN_REFRESHED" : "SIGNED_IN", session);
    return { data: { session }, error: null };
  } catch (error) {
    return { data: { session: null }, error: error as Error };
  }
}

async function refreshSession() {
  const current = read();
  if (!current?.refresh_token) return { data: { session: null }, error: new Error("No session") };

  // Share one in-flight refresh between concurrent callers
  refreshing ??= (async () => {
    try {
      const res = await fetch(`${API_URL}/api/auth/refresh-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: current.refresh_token }),
      });
      if (!res.ok) {
        write(null);
        emit("SIGNED_OUT", null);
        return null;
      }
      const body = await res.json();
      const next: Session = {
        ...current,
        access_token: body.session.access_token,
        refresh_token: body.session.refresh_token,
        expires_at: body.session.expires_at ?? jwtExp(body.session.access_token),
      };
      write(next);
      emit("TOKEN_REFRESHED", next);
      return next;
    } catch {
      return null;
    } finally {
      refreshing = null;
    }
  })();

  const session = await refreshing;
  return { data: { session }, error: session ? null : new Error("Refresh failed") };
}

async function getSession() {
  const session = read();
  // Refresh when the access token is expired or about to expire
  if (session && session.expires_at && session.expires_at - 30 < Date.now() / 1000) {
    return refreshSession();
  }
  return { data: { session }, error: null };
}

function onAuthStateChange(callback: Listener) {
  listeners.add(callback);
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) {
      const session = read();
      callback(session ? "SIGNED_IN" : "SIGNED_OUT", session);
    }
  };
  if (typeof window !== "undefined") window.addEventListener("storage", onStorage);
  return {
    data: {
      subscription: {
        unsubscribe: () => {
          listeners.delete(callback);
          if (typeof window !== "undefined") window.removeEventListener("storage", onStorage);
        },
      },
    },
  };
}

async function signOut() {
  const session = read();
  write(null);
  emit("SIGNED_OUT", null);
  if (session?.access_token) {
    fetch(`${API_URL}/api/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${session.access_token}` },
    }).catch(() => {});
  }
  return { error: null };
}

export const authClient = {
  auth: { getSession, setSession, refreshSession, onAuthStateChange, signOut },
};

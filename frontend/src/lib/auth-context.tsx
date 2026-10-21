"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { authClient } from "./auth-session";
import { apiClient } from "./api-client";
import type { User, Session } from "./auth-session";

interface AuthState {
  user: User | null;
  session: Session | null;
  loading: boolean;
}

export type AuthResult = {
  success: boolean;
  error?: string;
};

interface AuthContextType extends AuthState {
  signIn: (email: string, password: string) => Promise<AuthResult>;
  signUp: (email: string, password: string, fullName: string) => Promise<AuthResult>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    session: null,
    loading: true,
  });

  const syncToken = useCallback((session: Session | null) => {
    if (session?.access_token) {
      apiClient.setToken(session.access_token);
    } else {
      apiClient.clearToken();
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    authClient.auth.getSession().then(({ data: { session } }) => {
      if (cancelled) return;
      const user = session?.user ?? null;
      setState({ user, session, loading: false });
      syncToken(session);
    });

    const {
      data: { subscription },
    } = authClient.auth.onAuthStateChange((event, session) => {
      if (cancelled) return;
      const user = session?.user ?? null;
      setState({ user, session, loading: false });
      syncToken(session);
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, [syncToken]);

  const signIn = async (email: string, password: string): Promise<AuthResult> => {
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const result = await response.json();

      if (!response.ok || !result.success) {
        return {
          success: false,
          error: result?.message || result?.error?.message || "Invalid email or password",
        };
      }

      if (result.session?.access_token) {
        apiClient.setToken(result.session.access_token);
      }

      // Store backend session so getSession/onAuthStateChange see it immediately
      try {
        const backendSession = result.session;
        if (backendSession?.access_token && backendSession?.refresh_token) {
          const { data, error } = await authClient.auth.setSession({
            access_token: backendSession.access_token,
            refresh_token: backendSession.refresh_token,
          });
          if (!error && data.session?.user) {
            setState({ user: data.session.user, session: data.session, loading: false });
            syncToken(data.session);
          }
        }
      } catch {
        // best effort
      }

      return { success: true };
    } catch (err: any) {
      console.error("SignIn error:", err);
      return { success: false, error: err.message || "Login failed. Please try again." };
    }
  };

  const signUp = async (
    email: string,
    password: string,
    fullName: string
  ): Promise<AuthResult> => {
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${API_URL}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, full_name: fullName }),
      });

      const result = await response.json();

      if (!response.ok || !result.success) {
        return {
          success: false,
          error: result?.error?.message || result?.message || "Registration failed",
        };
      }

      // Account created; the user signs in on the login page.
      return { success: true };
    } catch (err: any) {
      console.error("SignUp exception:", err);

      return {
        success: false,
        error:
          err?.message && err.message !== "{}"
            ? err.message
            : "Registration failed. Please ensure the backend is running.",
      };
    }
  };
  const signOut = async () => {
    apiClient.clearToken();
    await authClient.auth.signOut();
  };

  return (
    <AuthContext.Provider
      value={{
        ...state,
        signIn,
        signUp,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Navbar } from "@/components/layout/navbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/alert";
import { useAuth, AuthResult } from "@/lib/auth-context";
import { Eye, EyeOff, ShieldCheck } from "lucide-react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [registered, setRegistered] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { user, loading, signIn } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user && !loading) {
      router.push("/dashboard");
    }
  }, [user, loading, router]);

  // Coming from sign-up: show a confirmation and pre-fill the email
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("registered") !== "1") return;
    setRegistered(true);
    try {
      const saved = sessionStorage.getItem("visionx.registeredEmail");
      if (saved) {
        setEmail(saved);
        sessionStorage.removeItem("visionx.registeredEmail");
      }
    } catch {
      // storage unavailable
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      const result: AuthResult = await signIn(email, password);
      if (!result.success) {
        setError(result.error || "Login failed");
        setIsSubmitting(false);
      }
    } catch (err: any) {
      setError(err.message || "Login failed");
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />

      <main className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-8">
        <div className="grid w-full max-w-4xl overflow-hidden rounded-2xl border border-border bg-surface lg:grid-cols-[0.95fr_1.05fr]">
          {/* Left Side */}
          <section className="relative hidden min-h-[500px] overflow-hidden bg-gradient-to-br from-primary via-primary-dark to-primary-dark p-8 text-white lg:flex lg:flex-col lg:justify-between">
            <div className="absolute inset-0">
              <div className="absolute -left-12 top-10 h-44 w-44 animate-pulse rounded-full bg-white/10 blur-2xl" />
              <div className="absolute bottom-10 right-4 h-40 w-40 animate-pulse rounded-full bg-primary/25 blur-2xl" />
              <div className="absolute left-1/3 top-1/2 h-28 w-28 animate-pulse rounded-full bg-white/10 blur-xl" />
              <div className="absolute right-1/4 top-20 h-20 w-20 rounded-full bg-primary/20 blur-xl" />
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.12),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(0,0,0,0.22),transparent_45%)]" />
              <div className="absolute inset-0 bg-black/10" />
            </div>

            <div className="relative z-10">
              <div className="mb-10 inline-flex rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs text-white/85">
                VisionX workspace
              </div>

              <h1 className="max-w-xs text-4xl font-semibold leading-tight tracking-tight">
                Welcome back
              </h1>

              <p className="mt-4 max-w-xs text-sm leading-6 text-white/80">
                Sign in to continue verifying digital evidence, reviewing
                reports, and managing your trust analysis history.
              </p>
            </div>

            <div className="relative z-10 grid grid-cols-3 gap-3">
              <StepBox active number="1" text="Sign in securely" />
              <StepBox number="2" text="Open dashboard" />
              <StepBox number="3" text="Continue analysis" />
            </div>
          </section>

          {/* Right Side */}
          <section className="flex items-center justify-center px-5 py-8 sm:px-8">
            <div className="w-full max-w-sm">
              <div className="mb-6 text-center">
                <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <ShieldCheck className="h-5 w-5" />
                </div>

                <h1 className="text-2xl font-bold text-text">
                  Welcome back
                </h1>

                <p className="mt-2 text-sm text-muted">
                  Sign in to your VisionX account.
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                {registered && !error && (
                  <Alert variant="success" title="Account created">
                    Please sign in with your new account.
                  </Alert>
                )}

                {error && (
                  <Alert variant="error" title="Error">
                    {error}
                  </Alert>
                )}

                <Input
                  label="Email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  disabled={isSubmitting}
                />

                <div className="relative">
                  <Input
                    label="Password"
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    disabled={isSubmitting}
                  />

                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-[38px] text-muted hover:text-text"
                    disabled={isSubmitting}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>

                <Button
                  type="submit"
                  className="w-full"
                  loading={isSubmitting}
                  disabled={isSubmitting}
                >
                  Sign In
                </Button>

                <div className="text-center text-sm">
                  <Link
                    href="/forgot-password"
                    className="text-primary hover:text-primary-dark"
                  >
                    Forgot password?
                  </Link>
                </div>

                <div className="text-center text-sm text-muted">
                  Don&apos;t have an account?{" "}
                  <Link
                    href="/register"
                    className="font-medium text-primary hover:text-primary-dark"
                  >
                    Sign up
                  </Link>
                </div>
              </form>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

function StepBox({
  number,
  text,
  active = false,
}: {
  number: string;
  text: string;
  active?: boolean;
}) {
  return (
    <div
      className={`min-h-[86px] rounded-xl border p-3 ${
        active
          ? "border-white bg-white text-primary-dark"
          : "border-white/20 bg-black/20 text-white"
      }`}
    >
      <div
        className={`mb-3 flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
          active ? "bg-primary text-white" : "bg-white/20 text-white"
        }`}
      >
        {number}
      </div>

      <p
        className={`text-xs leading-5 ${
          active ? "text-primary-dark" : "text-white/85"
        }`}
      >
        {text}
      </p>
    </div>
  );
}
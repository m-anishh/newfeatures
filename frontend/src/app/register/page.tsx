"use client";

import React, { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Navbar } from "@/components/layout/navbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/alert";
import { useAuth, AuthResult } from "@/lib/auth-context";
import { Eye, EyeOff, CheckCircle2 } from "lucide-react";

interface FormErrors {
  full_name?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
}

export default function RegisterPage() {
  const [formData, setFormData] = useState({
    full_name: "",
    email: "",
    password: "",
    confirmPassword: "",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const { user, loading, signUp } = useAuth();
  const router = useRouter();

  const passwordRequirements = useMemo(() => {
    return {
      minLength: formData.password.length >= 8,
      hasUppercase: /[A-Z]/.test(formData.password),
      hasLowercase: /[a-z]/.test(formData.password),
      hasNumber: /\d/.test(formData.password),
    };
  }, [formData.password]);

  const isPasswordValid = Object.values(passwordRequirements).every(Boolean);

  const validate = (): FormErrors => {
    const errors: FormErrors = {};

    if (!formData.full_name.trim()) {
      errors.full_name = "Full name is required";
    }

    if (!formData.email.trim()) {
      errors.email = "Email is required";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      errors.email = "Please enter a valid email address";
    }

    if (!formData.password) {
      errors.password = "Password is required";
    }

    if (formData.password !== formData.confirmPassword) {
      errors.confirmPassword = "Passwords do not match";
    }

    return errors;
  };

  const errors = validate();
  const isFormValid =
    formData.full_name.trim().length >= 2 &&
    !errors.email &&
    isPasswordValid &&
    formData.password === formData.confirmPassword;

  useEffect(() => {
    if (user && !loading) {
      router.push("/dashboard");
    }
  }, [user, loading, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      const result: AuthResult = await signUp(
        formData.email,
        formData.password,
        formData.full_name
      );

      if (!result.success) {
        setError(
          result.error || "We couldn't create your account. Please try again."
        );
        setIsSubmitting(false);
        return;
      }
      // Account created: send the user to sign in, with the email pre-filled
      try {
        sessionStorage.setItem("visionx.registeredEmail", formData.email);
      } catch {
        // storage unavailable; the login form just starts empty
      }
      router.push("/login?registered=1");
    } catch (err: any) {
      setError("We couldn't create your account. Please try again.");
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />

      <main className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-8">
        <div className="grid w-full max-w-4xl overflow-hidden rounded-2xl border border-border bg-surface lg:grid-cols-[0.95fr_1.05fr]">
          {/* Left Side */}
          <section className="relative hidden min-h-[520px] overflow-hidden bg-gradient-to-br from-primary via-primary-dark to-primary-dark p-8 text-white lg:flex lg:flex-col lg:justify-between">
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
                VisionX onboarding
              </div>

              <h1 className="max-w-xs text-4xl font-semibold leading-tight tracking-tight">
                Get started with us
              </h1>

              <p className="mt-4 max-w-xs text-sm leading-6 text-white/80">
                Set up your account and start checking digital evidence with
                explainable trust scores.
              </p>
            </div>

            <div className="relative z-10 grid grid-cols-3 gap-3">
              <StepBox active number="1" text="Sign up your account" />
              <StepBox number="2" text="Upload your first file" />
              <StepBox number="3" text="Review the result" />
            </div>
          </section>

          {/* Right Side */}
          <section className="flex items-center justify-center px-5 py-8 sm:px-8">
            <div className="w-full max-w-sm">
              <div className="mb-6 text-center">
                <h1 className="text-2xl font-bold text-text">
                  Create account
                </h1>
                <p className="mt-2 text-sm text-muted">
                  Start your journey with VisionX.
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                {error && typeof error === "string" && (
                  <Alert variant="error" title="Error">
                    {error}
                  </Alert>
                )}

                <Input
                  label="Full Name"
                  type="text"
                  value={formData.full_name}
                  onChange={(e) =>
                    setFormData({ ...formData, full_name: e.target.value })
                  }
                  onBlur={() =>
                    setTouched((prev) => ({ ...prev, full_name: true }))
                  }
                  placeholder="John Doe"
                  required
                  disabled={isSubmitting}
                  error={touched.full_name ? errors.full_name : undefined}
                />

                <Input
                  label="Email Address"
                  type="email"
                  value={formData.email}
                  onChange={(e) =>
                    setFormData({ ...formData, email: e.target.value })
                  }
                  onBlur={() =>
                    setTouched((prev) => ({ ...prev, email: true }))
                  }
                  placeholder="you@example.com"
                  required
                  disabled={isSubmitting}
                  error={touched.email ? errors.email : undefined}
                />

                <div>
                  <div className="relative">
                    <Input
                      label="Password"
                      type={showPassword ? "text" : "password"}
                      value={formData.password}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          password: e.target.value,
                        })
                      }
                      onBlur={() =>
                        setTouched((prev) => ({ ...prev, password: true }))
                      }
                      placeholder="••••••••"
                      required
                      disabled={isSubmitting}
                      error={touched.password ? errors.password : undefined}
                    />

                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-[38px] text-muted hover:text-text"
                      disabled={isSubmitting}
                      aria-label={
                        showPassword ? "Hide password" : "Show password"
                      }
                    >
                      {showPassword ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </button>
                  </div>

                  {formData.password && (
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <PasswordRequirement
                        met={passwordRequirements.minLength}
                        text="8+ characters"
                      />
                      <PasswordRequirement
                        met={passwordRequirements.hasUppercase}
                        text="Uppercase"
                      />
                      <PasswordRequirement
                        met={passwordRequirements.hasLowercase}
                        text="Lowercase"
                      />
                      <PasswordRequirement
                        met={passwordRequirements.hasNumber}
                        text="Number"
                      />
                    </div>
                  )}
                </div>

                <div className="relative">
                  <Input
                    label="Confirm Password"
                    type={showConfirmPassword ? "text" : "password"}
                    value={formData.confirmPassword}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        confirmPassword: e.target.value,
                      })
                    }
                    onBlur={() =>
                      setTouched((prev) => ({
                        ...prev,
                        confirmPassword: true,
                      }))
                    }
                    placeholder="••••••••"
                    required
                    disabled={isSubmitting}
                    error={
                      touched.confirmPassword
                        ? errors.confirmPassword
                        : undefined
                    }
                  />

                  <button
                    type="button"
                    onClick={() =>
                      setShowConfirmPassword(!showConfirmPassword)
                    }
                    className="absolute right-3 top-[38px] text-muted hover:text-text"
                    disabled={isSubmitting}
                    aria-label={
                      showConfirmPassword
                        ? "Hide confirm password"
                        : "Show confirm password"
                    }
                  >
                    {showConfirmPassword ? (
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
                  disabled={!isFormValid || isSubmitting}
                >
                  Create Account
                </Button>

                <div className="text-center text-sm text-muted">
                  Already have an account?{" "}
                  <Link
                    href="/login"
                    className="font-medium text-primary hover:text-primary-dark"
                  >
                    Sign in
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

function PasswordRequirement({ met, text }: { met: boolean; text: string }) {
  return (
    <div
      className={`flex items-center gap-1.5 text-xs ${
        met ? "text-success" : "text-muted"
      }`}
    >
      <div
        className={`flex h-3.5 w-3.5 items-center justify-center rounded-full border ${
          met ? "border-success bg-success text-white" : "border-border"
        }`}
      >
        {met && <CheckCircle2 className="h-2.5 w-2.5" />}
      </div>
      <span>{text}</span>
    </div>
  );
}
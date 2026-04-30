"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthAPI, getStoredSession } from "@/app/lib/auth";

function getSafeNextPath() {
  if (typeof window === "undefined") return "/dashboard";
  const next = new URLSearchParams(window.location.search).get("next");
  if (!next || !next.startsWith("/") || next.startsWith("//")) return "/dashboard";
  return next;
}

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;

    async function checkExistingSession() {
      const session = getStoredSession();
      if (!session?.access) {
        setCheckingSession(false);
        return;
      }

      try {
        const user = await AuthAPI.me();
        if (!cancelled && user.authenticated) {
          router.replace(getSafeNextPath());
          return;
        }
      } catch {
      }

      if (!cancelled) setCheckingSession(false);
    }

    checkExistingSession();
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const identifier = String(form.get("identifier") || "").trim();
    const password = String(form.get("password") || "");
    const remember = form.get("remember") === "on";

    setError(null);

    if (!identifier || !password) {
      setError("Please enter email or username and password.");
      return;
    }

    setLoading(true);

    try {
      await AuthAPI.login({
        identifier,
        password,
        remember,
      });
      router.replace(getSafeNextPath());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  if (checkingSession) {
    return (
      <main className="grid min-h-[100dvh] place-items-center bg-[#0c0520] text-sm text-white/70">
        Checking login...
      </main>
    );
  }

  return (
    <main className="min-h-[100dvh] bg-[#0c0520] text-white flex justify-center px-0 py-0 sm:px-6 sm:py-6 lg:items-center">
      <div className="w-full max-w-md mx-auto flex flex-col">
        <div className="flex-1 overflow-y-auto">
          <div className="relative mt-0 mb-0 w-full rounded-none border-0 bg-transparent p-6 shadow-none sm:mt-8 sm:mb-4 sm:rounded-3xl sm:border sm:border-white/10 sm:bg-white/5 sm:p-8 sm:shadow-[0_0_0_1px_rgba(255,255,255,0.02)]">
            <div className="hidden sm:block pointer-events-none absolute inset-0 rounded-3xl ring-1 ring-inset ring-fuchsia-500/20" />

            <div className="mb-6 text-center">
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight">
                <span className="text-pink-400">ROBOT</span>{" "}
                <span className="text-sky-300">CONTROL</span>{" "}
                <span className="text-indigo-400">LOGIN</span>
              </h1>

              <p className="mt-2 text-sm text-white/70">Sign in to continue</p>
            </div>

            <form onSubmit={onSubmit} className="space-y-5">
              <div>
                <FieldLabel htmlFor="identifier">Email or username</FieldLabel>
                <div className="relative mt-1">
                  <input
                    id="identifier"
                    name="identifier"
                    type="text"
                    placeholder="you@example.com"
                    className="w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 text-sm outline-none placeholder:text-white/40 focus:border-fuchsia-400/50 focus:ring-2 focus:ring-fuchsia-400/30 sm:text-base"
                    autoComplete="username"
                    inputMode="email"
                  />
                  <div className="pointer-events-none absolute inset-0 rounded-xl ring-1 ring-inset ring-white/5" />
                </div>
              </div>

              <div>
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <div className="relative mt-1">
                  <input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="Enter password"
                    className="w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 pr-16 text-sm outline-none placeholder:text-white/40 focus:border-indigo-400/50 focus:ring-2 focus:ring-indigo-400/30 sm:text-base"
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((s) => !s)}
                    className="cursor-pointer absolute right-2 top-1/2 -translate-y-1/2 rounded-lg border border-white/10 bg-white/5 px-3 py-1 text-xs hover:bg-white/10"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? "Hide" : "Show"}
                  </button>
                </div>
              </div>

              <label className="inline-flex items-center gap-2 select-none text-xs sm:text-sm">
                <input
                  type="checkbox"
                  name="remember"
                  defaultChecked
                  className="h-3 w-3 accent-fuchsia-400 sm:h-4 sm:w-4"
                />
                <span className="text-white/80">Remember me</span>
              </label>

              {error && (
                <p className="text-xs sm:text-sm text-rose-300 bg-rose-500/10 border border-rose-400/30 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={loading}
                className="cursor-pointer w-full rounded-xl border border-fuchsia-400/40 bg-gradient-to-r from-pink-500/30 via-indigo-500/30 to-sky-500/30 px-4 py-3 text-sm font-semibold hover:from-pink-500/40 hover:via-indigo-500/40 hover:to-sky-500/40 disabled:cursor-not-allowed disabled:opacity-60 sm:text-base"
              >
                {loading ? "Signing in..." : "Sign in"}
              </button>
            </form>
          </div>

          <p className="mt-4 sm:mt-6 text-center text-[11px] sm:text-xs text-white/50">
            Don&apos;t have an account?{" "}
            <Link href="/register" className="text-sky-300 hover:text-sky-200">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}

function FieldLabel({
  children,
  htmlFor,
}: {
  children: React.ReactNode;
  htmlFor: string;
}) {
  return (
    <label htmlFor={htmlFor} className="block text-xs sm:text-sm font-medium text-white/80">
      {children}
    </label>
  );
}

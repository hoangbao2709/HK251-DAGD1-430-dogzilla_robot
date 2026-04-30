"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AuthAPI } from "@/app/lib/auth";

type FieldLabelProps = {
  children: React.ReactNode;
  htmlFor: string;
};

function FieldLabel({ children, htmlFor }: FieldLabelProps) {
  return (
    <label htmlFor={htmlFor} className="block text-sm font-medium text-white/80">
      {children}
    </label>
  );
}

export default function RegisterPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const username = String(data.get("username") || "").trim();
    const email = String(data.get("email") || "").trim();
    const password = String(data.get("password") || "");
    const confirmPassword = String(data.get("confirmPassword") || "");

    setError(null);

    if (!username || !email || !password || !confirmPassword) {
      setError("Please fill in all fields.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }

    setLoading(true);

    try {
      await AuthAPI.register({ username, email, password });
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Register failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#0c0520] text-white grid place-items-center p-6">
      <div className="w-full max-w-md">
        <div className="relative rounded-3xl border border-white/10 bg-white/5 p-6 shadow-[0_0_0_1px_rgba(255,255,255,0.02)] sm:p-8">
          <div className="pointer-events-none absolute inset-0 rounded-3xl ring-1 ring-inset ring-sky-500/20" />
          <div className="mb-6 text-center">
            <div className="inline-flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-sky-400 shadow-[0_0_20px_2px_rgba(56,189,248,0.6)]" />
              <h1 className="text-2xl font-bold tracking-tight">
                <span className="text-pink-400">ROBOT</span>{" "}
                <span className="text-sky-300">CONTROL</span>{" "}
                <span className="text-indigo-400">SIGN UP</span>
              </h1>
            </div>
            <p className="mt-2 text-sm text-white/70">
              Create an account to access Robot Control.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-5">
            <div>
              <FieldLabel htmlFor="username">Username</FieldLabel>
              <div className="relative mt-1">
                <input
                  id="username"
                  name="username"
                  type="text"
                  placeholder="yourname"
                  className="w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 outline-none placeholder:text-white/40 focus:border-fuchsia-400/50 focus:ring-2 focus:ring-fuchsia-400/30"
                  autoComplete="username"
                />
              </div>
            </div>
            <div>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <div className="relative mt-1">
                <input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="you@example.com"
                  className="w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 outline-none placeholder:text-white/40 focus:border-fuchsia-400/50 focus:ring-2 focus:ring-fuchsia-400/30"
                  autoComplete="email"
                />
              </div>
            </div>
            <div>
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <div className="relative mt-1">
                <input
                  id="password"
                  name="password"
                  type="password"
                  placeholder="Enter password"
                  className="w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 outline-none placeholder:text-white/40 focus:border-indigo-400/50 focus:ring-2 focus:ring-indigo-400/30"
                  autoComplete="new-password"
                />
              </div>
            </div>
            <div>
              <FieldLabel htmlFor="confirmPassword">Confirm password</FieldLabel>
              <div className="relative mt-1">
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  placeholder="Confirm password"
                  className="w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 outline-none placeholder:text-white/40 focus:border-indigo-400/50 focus:ring-2 focus:ring-indigo-400/30"
                  autoComplete="new-password"
                />
              </div>
            </div>

            {error && (
              <p className="text-sm text-rose-300 bg-rose-500/10 border border-rose-400/30 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="cursor-pointer w-full rounded-xl border border-sky-400/40 bg-gradient-to-r from-sky-500/30 via-indigo-500/30 to-pink-500/30 px-4 py-3 font-semibold hover:from-sky-500/40 hover:via-indigo-500/40 hover:to-pink-500/40 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? "Creating account..." : "Create account"}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-white/50">
          Already have an account?{" "}
          <Link href="/login" className="text-sky-300 hover:text-sky-200">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}

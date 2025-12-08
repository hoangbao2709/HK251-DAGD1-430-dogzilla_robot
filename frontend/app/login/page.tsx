"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

// Để thống nhất với Dashboard: dùng chung BACKEND_BASE
const BACKEND_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const email = String(data.get("email") || "").trim();
    const password = String(data.get("password") || "");

    setError(null);

    if (!email || !password) {
      setError("Please enter email and password.");
      return;
    }

    setLoading(true);

    try {
      const res = await fetch(`${BACKEND_BASE}/api/auth/login/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const json = await res.json().catch(() => ({} as any));
      console.log("[login] status =", res.status);
      console.log("[login] json =", json);

      if (!res.ok || json.ok === false) {
        setError(json.error || json.detail || "Login failed");
        return;
      }

      const accessToken: string | null =
        json.access || json.token || json.access_token || null;
      const refreshToken: string | null =
        json.refresh || json.refresh_token || null;

      if (!accessToken) {
        setError("Cannot find access token in response.");
        return;
      }

      if (typeof window !== "undefined") {
        localStorage.setItem("access_token", accessToken);
        if (refreshToken) {
          localStorage.setItem("refresh_token", refreshToken);
        }
        if (json.username) {
          localStorage.setItem("username", json.username);
        }
        if (json.email) {
          localStorage.setItem("user_email", json.email);
        }
        if (json.robot_url) {
          localStorage.setItem("robot_url", json.robot_url);
        }
        if (json.robot_device_id) {
          localStorage.setItem("robot_device_id", json.robot_device_id);
        }
      }

      router.push("/dashboard");
    } catch (err) {
      console.error(err);
      setError("Network error, please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      className="
    min-h-[100dvh]
    bg-[#0c0520] text-white
    flex justify-center
    px-0 sm:px-6
    py-0 sm:py-6
    lg:items-center
  "
    >
      <div className="w-full max-w-md mx-auto flex flex-col">
        <div className="flex-1 overflow-y-auto">

          {/* CARD: MOBILE = full width, PC = card */}
          <div
            className="
          mt-0 sm:mt-8 mb-0 sm:mb-4
          w-full
          
          /* MOBILE style (no rounded, no border, full width) */
          rounded-none border-0 shadow-none bg-transparent p-6

          /* DESKTOP style */
          sm:rounded-3xl sm:border sm:border-white/10 sm:bg-white/5
          sm:shadow-[0_0_0_1px_rgba(255,255,255,0.02)]
          sm:p-8
        "
          >
            {/* Ring chỉ hiện trên PC */}
            <div className="hidden sm:block pointer-events-none absolute inset-0 rounded-3xl ring-1 ring-inset ring-fuchsia-500/20" />

            <div className="mb-6 text-center">
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight">
                <span className="text-pink-400">ROBOT</span>{" "}
                <span className="text-sky-300">CONTROL</span>{" "}
                <span className="text-indigo-400">LOGIN</span>
              </h1>

              <p className="mt-2 text-sm text-white/70">
                Sign in to continue
              </p>
            </div>

            <form onSubmit={onSubmit} className="space-y-5">

              <FieldLabel htmlFor="email">Email</FieldLabel>
              <div className="relative">
                <input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="you@example.com"
                  className="w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 text-sm sm:text-base outline-none placeholder:text-white/40 focus:border-fuchsia-400/50 focus:ring-2 focus:ring-fuchsia-400/30"
                  autoComplete="email"
                  inputMode="email"
                />
                <div className="pointer-events-none absolute inset-0 rounded-xl ring-1 ring-inset ring-white/5" />
              </div>

              <FieldLabel htmlFor="password">Password</FieldLabel>
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  className="w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 pr-16 text-sm sm:text-base outline-none placeholder:text-white/40 focus:border-indigo-400/50 focus:ring-2 focus:ring-indigo-400/30"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((s) => !s)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg px-3 py-1 text-xs bg-white/5 border border-white/10 hover:bg-white/10"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>

              <div className="flex items-center justify-between text-xs sm:text-sm">
                <label className="inline-flex items-center gap-2 select-none">
                  <input
                    type="checkbox"
                    name="remember"
                    className="accent-fuchsia-400 h-3 w-3 sm:h-4 sm:w-4"
                  />
                  <span className="text-white/80">Remember me</span>
                </label>
                <a
                  href="#"
                  className="text-sky-300 hover:text-sky-200 whitespace-nowrap"
                >
                  Forgot password?
                </a>
              </div>

              {error && (
                <p className="text-xs sm:text-sm text-rose-300 bg-rose-500/10 border border-rose-400/30 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-xl border border-fuchsia-400/40 bg-gradient-to-r from-pink-500/30 via-indigo-500/30 to-sky-500/30 px-4 py-3 text-sm sm:text-base font-semibold hover:from-pink-500/40 hover:via-indigo-500/40 hover:to-sky-500/40 disabled:opacity-60"
              >
                {loading ? "Signing in..." : "Sign in"}
              </button>

              <div className="relative py-2 sm:py-3 text-center">
                <div className="border-t border-white/10" />
                <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-[#0c0520] px-3 text-[10px] sm:text-xs text-white/60">
                  or
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  className="rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-xs sm:text-sm hover:bg-white/10"
                >
                  Login with Google
                </button>
                <button
                  type="button"
                  className="rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-xs sm:text-sm hover:bg-white/10"
                >
                  Login with GitHub
                </button>
              </div>
            </form>
          </div>

          <p className="mt-4 sm:mt-6 text-center text-[11px] sm:text-xs text-white/50">
            Don&apos;t have an account?{" "}
            <a href="/register" className="text-sky-300 hover:text-sky-200">
              Create one
            </a>
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
    <label
      htmlFor={htmlFor}
      className="block text-xs sm:text-sm font-medium text-white/80"
    >
      {children}
    </label>
  );
}

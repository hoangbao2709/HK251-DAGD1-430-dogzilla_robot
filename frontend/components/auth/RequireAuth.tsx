"use client";

import { useEffect } from "react";
import { AuthAPI, clearAuthSession, getStoredSession } from "@/app/lib/auth";

export default function RequireAuth({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    async function checkAuthOptional() {
      const session = getStoredSession();

      if (!session?.access) {
        return;
      }

      try {
        const user = await AuthAPI.me();

        if (!user.authenticated) {
          clearAuthSession();
        }
      } catch {
        clearAuthSession();
      }
    }

    checkAuthOptional();
  }, []);

  return <>{children}</>;
}
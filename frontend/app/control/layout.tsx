import React, { Suspense } from "react";
import RequireAuth from "@/components/auth/RequireAuth";

export default function ControlLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <Suspense fallback={<div className="p-6">Loading control...</div>}>
        {children}
      </Suspense>
    </RequireAuth>
  );
}

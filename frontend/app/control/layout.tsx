import React, { Suspense } from "react";

export default function ControlLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="p-6">Loading control...</div>}>
      {children}
    </Suspense>
  );
}

import Sidebar from "@/components/Sidebar";

export default function AutonomousLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(253,116,155,0.12),transparent_32%),radial-gradient(circle_at_top_right,rgba(0,194,255,0.10),transparent_28%),radial-gradient(circle_at_bottom_left,rgba(124,77,255,0.10),transparent_30%)] dark:bg-[radial-gradient(circle_at_top_left,rgba(253,116,155,0.10),transparent_30%),radial-gradient(circle_at_top_right,rgba(0,194,255,0.08),transparent_26%),radial-gradient(circle_at_bottom_left,rgba(124,77,255,0.08),transparent_28%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-white/40 via-white/10 to-transparent dark:from-white/6 dark:via-white/0" />

      <div className="relative flex min-h-screen flex-row">
        <div className="hidden sm:block">
          <Sidebar />
        </div>

        <div className="flex flex-1 flex-col">
          <main className="flex-1 overflow-y-auto">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}

import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-[#1A0F28] text-white">
      <div className="flex min-h-screen flex-row">
        {/* Sidebar: ẩn trên màn hình rất nhỏ (thường là điện thoại dọc),
            vẫn hiện khi đủ rộng (sm trở lên, tức điện thoại quay ngang, tablet, PC) */}
        <div className="hidden sm:block">
          <Sidebar />
        </div>

        <div className="flex flex-col flex-1">
          <Topbar />
          {/* main để children tự quyết định padding (Dashboard dùng p-4 md:p-6) */}
          <main className="flex-1 overflow-y-auto">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}

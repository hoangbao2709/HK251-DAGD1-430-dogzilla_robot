"use client"; // bắt buộc vì chúng ta dùng hook

import RobotCamera from "@/components/RobotCamera"; 
import { useSearchParams } from "next/navigation";

export default function TestLinePage() {
  const searchParams = useSearchParams();
  const ip = searchParams.get("ip"); 
  const robotId = "robot-a"; 

  if (!ip) return <div>Không có IP robot</div>;

  return (
    <div style={{ padding: 20 }}>
      <h1>Test Line Tracking</h1>
      <RobotCamera robotId={robotId} interval={200} />
    </div>
  );
}
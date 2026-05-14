"use client";
import { useEffect, useState } from "react";

type RobotCameraProps = {
  robotId: string;
  interval?: number;
};

type CameraTracking = {
  found?: boolean;
  cx?: number;
  cy?: number;
  error?: number;
  linear_x?: number;
  angular_z?: number;
};

export default function RobotCamera({ robotId, interval = 500 }: RobotCameraProps) {
  const [frame, setFrame] = useState<string | null>(null);
  const [mask, setMask] = useState<string | null>(null);
  const [tracking, setTracking] = useState<CameraTracking | null>(null);
  const formatNumber = (value: number | undefined, digits = 3) =>
    typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "-";

  useEffect(() => {
    let isMounted = true;
    let inFlight = false;

    const fetchFrame = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await fetch(`http://localhost:8000/control/api/robots/${robotId}/camera/`);
        const data = await res.json();
        if (!isMounted) return;
        if (data.ok) {
          setFrame(data.frame);
          setMask(data.mask);
          setTracking(data.tracking);
        }
      } catch (err) {
        console.error(err);
      } finally {
        inFlight = false;
      }
    };

    fetchFrame();
    const id = setInterval(fetchFrame, interval);
    return () => {
      isMounted = false;
      clearInterval(id);
    };
  }, [robotId, interval]);

  return (
    <div style={{ display: "flex", gap: 10 }}>
      {frame && <img src={`data:image/jpeg;base64,${frame}`} width={320} height={240} />}
      {mask && <img src={`data:image/jpeg;base64,${mask}`} width={320} height={240} style={{opacity:0.5}} />}
      {tracking && tracking.found && (
        <div style={{color:"white"}}>
          <p>cx: {tracking.cx}</p>
          <p>cy: {tracking.cy}</p>
          <p>error: {formatNumber(tracking.error)}</p>
          <p>linear_x: {formatNumber(tracking.linear_x)}</p>
          <p>angular_z: {formatNumber(tracking.angular_z)}</p>
        </div>
      )}
    </div>
  );
}

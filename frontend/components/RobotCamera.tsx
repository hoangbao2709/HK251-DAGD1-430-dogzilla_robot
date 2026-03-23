"use client";
import { useEffect, useState } from "react";

export default function RobotCamera({ robotId, interval = 100 }) {
  const [frame, setFrame] = useState<string | null>(null);
  const [mask, setMask] = useState<string | null>(null);
  const [tracking, setTracking] = useState<any>(null);

  useEffect(() => {
    let isMounted = true;

    const fetchFrame = async () => {
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
          <p>error: {tracking.error.toFixed(3)}</p>
          <p>linear_x: {tracking.linear_x.toFixed(3)}</p>
          <p>angular_z: {tracking.angular_z.toFixed(3)}</p>
        </div>
      )}
    </div>
  );
}
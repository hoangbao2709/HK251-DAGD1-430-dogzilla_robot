const els = {
  status: document.getElementById("status"),
  x_bottom: document.getElementById("x_bottom"),
  x_mid: document.getElementById("x_mid"),
  x_top: document.getElementById("x_top"),
  e_lat: document.getElementById("e_lat"),
  e_heading: document.getElementById("e_heading"),
  e_mix: document.getElementById("e_mix"),
  forward: document.getElementById("forward"),
  turn: document.getElementById("turn"),
  robotResponse: document.getElementById("robotResponse"),
  trackingStatus: document.getElementById("trackingStatus"),
  pauseBtn: document.getElementById("pauseBtn"),
  resumeBtn: document.getElementById("resumeBtn"),
};

function setText(el, value) {
  el.textContent = value === null || value === undefined ? "None" : String(value);
}

async function fetchState() {
  try {
    const res = await fetch("/state");
    const state = await res.json();

    setText(els.status, state.status);
    setText(els.x_bottom, state.x_bottom);
    setText(els.x_mid, state.x_mid);
    setText(els.x_top, state.x_top);
    setText(els.e_lat, state.e_lat);
    setText(els.e_heading, state.e_heading);
    setText(els.e_mix, state.e_mix);
    setText(els.forward, state.forward);
    setText(els.turn, state.turn);

    els.robotResponse.textContent = JSON.stringify(state.robot_response, null, 2);
    els.trackingStatus.textContent = state.tracking_enabled ? "RUNNING" : "PAUSED";

    if (state.tracking_enabled) {
      els.trackingStatus.className = "status-running";
    } else {
      els.trackingStatus.className = "status-paused";
    }

  } catch (err) {
    console.error(err);
  }
}

async function pauseTracking() {
  try {
    const res = await fetch("/tracking/pause", {
      method: "POST"
    });
    const data = await res.json();
    console.log("pause:", data);
    fetchState();
  } catch (err) {
    console.error(err);
  }
}

async function resumeTracking() {
  try {
    const res = await fetch("/tracking/resume", {
      method: "POST"
    });
    const data = await res.json();
    console.log("resume:", data);
    fetchState();
  } catch (err) {
    console.error(err);
  }
}

els.pauseBtn.addEventListener("click", pauseTracking);
els.resumeBtn.addEventListener("click", resumeTracking);

setInterval(fetchState, 150);
fetchState();
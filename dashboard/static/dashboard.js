const statusNames = ["NORMAL", "CAUTION", "HIGH RISK", "CRITICAL", "NOT DETECTED"];

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function formatTime(value) {
  if (!value) return "Waiting for engine";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function drawChart(canvas, series, options = {}) {
  const bounds = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(100, Math.floor(bounds.width));
  const height = Math.max(120, Math.floor(bounds.height));
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);

  const pad = { left: 34, right: 12, top: 12, bottom: 25 };
  const chartWidth = width - pad.left - pad.right;
  const chartHeight = height - pad.top - pad.bottom;
  context.font = "10px Segoe UI, Arial";
  context.lineWidth = 1;
  context.strokeStyle = "#26354d";
  context.fillStyle = "#91a0b7";
  for (let tick = 0; tick <= 4; tick += 1) {
    const value = options.maxValue * tick / 4;
    const y = pad.top + chartHeight - chartHeight * tick / 4;
    context.beginPath();
    context.moveTo(pad.left, y);
    context.lineTo(width - pad.right, y);
    context.stroke();
    context.fillText(String(Math.round(value)), 2, y + 3);
  }
  if (!series.length) {
    context.fillText("Waiting for data", pad.left + 8, pad.top + chartHeight / 2);
    return;
  }

  if (options.bars) {
    const slot = chartWidth / series.length;
    const barWidth = Math.max(3, slot * 0.55);
    series.forEach((point, index) => {
      const value = Math.max(0, Math.min(options.maxValue, point.value));
      const barHeight = chartHeight * value / options.maxValue;
      const x = pad.left + slot * index + (slot - barWidth) / 2;
      const y = pad.top + chartHeight - barHeight;
      context.fillStyle = options.color;
      context.fillRect(x, y, barWidth, barHeight);
      if (point.label) {
        context.fillStyle = "#91a0b7";
        const labelWidth = context.measureText(point.label).width;
        context.fillText(point.label, x + (barWidth - labelWidth) / 2, height - 6);
      }
    });
  } else {
    context.beginPath();
    series.forEach((point, index) => {
      const x = pad.left + chartWidth * index / Math.max(1, series.length - 1);
      const value = Math.max(0, Math.min(options.maxValue, point.value));
      const y = pad.top + chartHeight - chartHeight * value / options.maxValue;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.strokeStyle = options.color;
    context.lineWidth = 2;
    context.stroke();
    const ticks = Math.min(5, series.length);
    for (let tick = 0; tick < ticks; tick += 1) {
      const index = Math.round((series.length - 1) * tick / Math.max(1, ticks - 1));
      const x = pad.left + chartWidth * index / Math.max(1, series.length - 1);
      const label = series[index].label || "";
      const labelWidth = context.measureText(label).width;
      context.fillText(label, Math.max(pad.left, x - labelWidth / 2), height - 6);
    }
  }
}

function eventDescription(event) {
  const behavior = [];
  if (event.eye_closed) behavior.push("eye closure");
  if (event.yawning) behavior.push("yawn");
  if (event.head_nodding) behavior.push("head nod");
  if (behavior.length) return behavior.join(", ");
  if (event.fatigue_level === "NOT DETECTED") return "Face unavailable";
  return event.reason || (event.event_type === "status" ? "Status change" : "Recorded event");
}

function renderHistory(events) {
  const rows = document.getElementById("historyRows");
  rows.replaceChildren();
  setText("eventCount", `${events.length} recent event${events.length === 1 ? "" : "s"}`);
  if (!events.length) {
    const row = rows.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 6;
    cell.className = "empty-row";
    cell.textContent = "No events recorded yet.";
    return;
  }
  events.forEach((event) => {
    const row = rows.insertRow();
    const values = [
      formatTime(event.timestamp),
      event.fatigue_level,
      event.fatigue_level === "NOT DETECTED" ? "—" : `${event.risk_score}/100`,
      Number(event.ear || 0).toFixed(3),
      `${Number(event.perclos || 0).toFixed(1)}%`,
    ];
    values.forEach((value) => {
      const cell = row.insertCell();
      cell.textContent = value;
    });
    const eventCell = row.insertCell();
    const badge = document.createElement("span");
    badge.className = "event-pill";
    badge.textContent = eventDescription(event);
    eventCell.appendChild(badge);
  });
}

async function updateDashboard() {
  try {
    const [statusResponse, analyticsResponse, historyResponse, sessionsResponse] = await Promise.all([
      fetch("/api/status", { cache: "no-store" }),
      fetch("/api/analytics", { cache: "no-store" }),
      fetch("/api/history?limit=12", { cache: "no-store" }),
      fetch("/api/sessions", { cache: "no-store" }),
    ]);
    if (!statusResponse.ok || !analyticsResponse.ok || !historyResponse.ok || !sessionsResponse.ok) {
      throw new Error("Dashboard API returned an unsuccessful response");
    }
    const [status, analytics, events, sessions] = await Promise.all([
      statusResponse.json(),
      analyticsResponse.json(),
      historyResponse.json(),
      sessionsResponse.json(),
    ]);

    const statusElement = document.getElementById("statusValue");
    statusElement.textContent = status.status;
    statusElement.className = `status-value ${status.status.toLowerCase().replaceAll(" ", "-")}`;
    setText("statusMessage", status.message || status.reasons.join(", ") || "Monitoring status");
    const hasRiskScore = status.face_detected && !status.calibrating &&
      status.status !== "NOT DETECTED";
    setText("riskValue", hasRiskScore ? status.risk_score : "—");
    setText("riskHint", status.calibrating ? "Personalising eye-closure threshold" :
      (status.face_detected ? "Live facial measurements" : "No face detected"));
    const riskBar = document.getElementById("riskBar");
    riskBar.style.width = `${hasRiskScore ? Math.max(0, Math.min(100, status.risk_score)) : 0}%`;
    riskBar.style.background = !hasRiskScore ? "#26354b" :
      status.risk_score >= 75 ? "#ff6b75" :
        status.risk_score >= 50 ? "#ffc857" : "#55d6be";

    const engine = document.getElementById("engineIndicator");
    engine.classList.toggle("online", status.engine_running);
    engine.querySelector("span").textContent = status.engine_running ? "ENGINE ONLINE" : "ENGINE OFFLINE";
    document.querySelector(".live-dot").classList.toggle("offline", !status.engine_running);
    setText("cameraValue", status.engine_running ? (status.calibrating ? "CALIBRATING" : "ONLINE") : "OFFLINE");
    setText("faceValue", status.face_detected ? "YES" : "NO");
    setText("arduinoValue", status.arduino_status || "DISCONNECTED");
    setText("earValue", Number(status.ear || 0).toFixed(3));
    setText("marValue", Number(status.mar || 0).toFixed(3));
    setText("perclosValue", `${Number(status.perclos || 0).toFixed(1)}%`);
    setText("closuresValue", status.eye_closures || 0);
    setText("yawnsValue", status.yawning_count || 0);
    setText("nodsValue", status.head_nodding_count || 0);
    setText("updatedAt", formatTime(status.updated_at));

    drawChart(
      document.getElementById("riskChart"),
      analytics.samples.map((sample) => ({
        value: Number(sample.risk_score),
        label: new Date(sample.timestamp).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
      })),
      { maxValue: 100, color: "#70a6ff" },
    );
    const severityLevels = ["CAUTION", "HIGH RISK", "CRITICAL"];
    const severity = severityLevels.map((level) => ({
      label: level,
      value: Number(sessions.severity_counts[level] || 0),
    }));
    drawChart(document.getElementById("severityChart"), severity, {
      maxValue: Math.max(4, ...severity.map((point) => point.value)),
      color: "#ff6b75",
      bars: true,
    });
    renderHistory(events);
  } catch (error) {
    setText("statusMessage", error.message);
  }
}

updateDashboard();
window.setInterval(updateDashboard, 1500);
window.addEventListener("resize", updateDashboard);

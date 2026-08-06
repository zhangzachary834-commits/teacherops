let rawState = {
  data: null,
  selectedInquiryId: "",
  selectedMatchId: "",
  selectedLeaveId: "",
  teacherFilter: ""
};

try {
  const saved = localStorage.getItem("tutorAppState");
  if (saved) {
    const parsed = JSON.parse(saved);
    Object.assign(rawState, parsed);
  }
} catch (e) {}

const appState = new Proxy(rawState, {
  set(target, property, value) {
    target[property] = value;
    if (property !== "data") {
      const stateToSave = {
        selectedInquiryId: target.selectedInquiryId,
        selectedMatchId: target.selectedMatchId,
        selectedLeaveId: target.selectedLeaveId,
        teacherFilter: target.teacherFilter,
      };
      localStorage.setItem("tutorAppState", JSON.stringify(stateToSave));
    }
    return true;
  }
});
function setStatus(text, isError = false) {
  const statusEl = document.querySelector("#status");
  if (!statusEl) return;
  statusEl.textContent = text;
  statusEl.className = isError ? "status error" : "status";
}

async function api(path, options = {}) {
  const token = localStorage.getItem("token");
  const headers = { 
    "Content-Type": "application/json",
    "Cache-Control": "no-cache, no-store, must-revalidate",
    ...(options.headers || {})
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(path, {
    ...options,
    headers
  });

  if (response.status === 401) {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    if (!window.location.pathname.includes("login.html") && !window.location.pathname.includes("register.html")) {
      window.location.href = "/login.html";
      return null;
    }
  }

  const raw = await response.text();
  let data = {};
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch (error) {
    throw new Error(response.ok ? "Server returned invalid JSON." : raw || "Request failed");
  }
  if (!response.ok || data.error) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

function textList(items) {
  if (!items || items.length === 0) return "-";
  return items.map(item => escapeHtml(item)).join(", ");
}

function displayText(value, fallback = "") {
  const text = value === undefined || value === null || value === "" ? fallback : value;
  return escapeHtml(text);
}

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function formatDate(isoString) {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return escapeHtml(isoString);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  } catch (e) {
    return escapeHtml(isoString);
  }
}

async function loadState() {
  appState.data = await api("/api/state");
  const role = appState.data.role;
  const profileId = appState.data.profile_id;
  
  if (!profileId && (role === "teacher" || role === "parent")) {
    const existing = document.getElementById("empty-state-banner");
    if (!existing) {
      const banner = document.createElement("div");
      banner.id = "empty-state-banner";
      banner.className = "record secondary";
      banner.style = "margin: 16px; text-align: center;";
      banner.innerHTML = "<h3>Welcome!</h3><p>Please fill out your profile form below to get started.</p>";
      const main = document.querySelector("main");
      if (main) main.prepend(banner);
    }
  } else {
    const banner = document.getElementById("empty-state-banner");
    if (banner) banner.remove();
  }
  
  return appState.data;
}

async function submitJson(form, path, successText, onSuccess) {
  try {
    await api(path, {
      method: "POST",
      body: JSON.stringify(formData(form))
    });
    form.reset();
    await loadState();
    if (typeof onSuccess === "function") {
      onSuccess();
    }
    setStatus(successText);
  } catch (error) {
    setStatus(`Error: ${error.message}`, true);
  }
}

function bindRefreshButton(onRefresh) {
  const button = document.querySelector("#refreshButton");
  if (!button) return;
  button.addEventListener("click", () => {
    onRefresh().catch(error => setStatus(error.message, true));
  });
}

async function archiveRecord(recordType, recordId) {
  try {
    await api("/api/archive", {
      method: "POST",
      body: JSON.stringify({ record_type: recordType, record_id: recordId })
    });
    setStatus(`Archived ${recordId} successfully`);
    await loadState();
    if (typeof window.refreshDashboard === "function") {
      window.refreshDashboard();
    }
  } catch (err) {
    setStatus(`Failed to archive ${recordId}: ${err.message}`, true);
  }
}

function renderMetrics(summary) {
  const metricsEl = document.querySelector("#metrics");
  if (!metricsEl || !summary) return;

  const metrics = [
    ["Teachers", summary.teachers_total],
    ["New inquiries", summary.new_inquiries_this_week],
    ["Trials scheduled", summary.trial_scheduled],
    ["Follow-ups", summary.followups_needed],
    ["Leave requests", summary.open_leave_requests],
    ["Doc updates", summary.google_doc_updates_needed]
  ];

  metricsEl.innerHTML = metrics.map(([label, value]) => `
    <div class="metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value ?? 0)}</strong>
    </div>
  `).join("");
}

function renderInquiries(inquiries, options = {}) {
  const container = document.querySelector("#inquiries");
  if (!container) return;

  const selectable = options.selectable !== false;
  const filtered = options.filterStudent
    ? inquiries.filter(inquiry => (inquiry.student_name || "").toLowerCase().includes(options.filterStudent.toLowerCase()))
    : inquiries;

  container.innerHTML = filtered.map(inquiry => {
    const selected = appState.selectedInquiryId === inquiry.id ? "selected" : "";
    const tag = selectable ? "button" : "div";
    const attrs = selectable
      ? `class="record secondary ${selected}" data-inquiry-id="${escapeAttribute(inquiry.id)}" type="button"`
      : `class="record ${selected}"`;

    return `
      <${tag} ${attrs}>
        <div class="row">
          <h3>${displayText(inquiry.id)} ${displayText(inquiry.parent_name, "Unknown parent")}</h3>
          <span class="pill green">${displayText(inquiry.status, "need_teacher")}</span>
        </div>
        <div class="muted">${displayText(inquiry.student_name, "Student")} / ${displayText(inquiry.subject, "subject open")} / ${displayText(inquiry.level, "level open")}</div>
        <div class="muted">${textList(inquiry.availability)}</div>
        <div class="muted" style="font-size: 0.8em; text-align: right; margin-top: 4px;">Added: ${formatDate(inquiry.created_at)}</div>
        ${(localStorage.getItem("role") === "admin" || localStorage.getItem("role") === "developer") ? `<button type="button" style="margin-top:8px; font-size:0.8em;" onclick="event.stopPropagation(); archiveRecord('inquiry', '${escapeAttribute(inquiry.id)}')">Archive</button>` : ""}
      </${tag}>
    `;
  }).join("") || `<div class="record muted">No inquiries yet.</div>`;

  if (!selectable) return;

  container.querySelectorAll("[data-inquiry-id]").forEach(button => {
    button.addEventListener("click", () => {
      appState.selectedInquiryId = button.dataset.inquiryId;
      const inquiry = appState.data.inquiries.find(item => item.id === appState.selectedInquiryId);
      const label = document.querySelector("#selectedInquiryLabel");
      if (label) {
        label.textContent = inquiry ? inquiry.id : "No inquiry selected";
      }
      if (typeof options.onSelect === "function") {
        options.onSelect();
      }
    });
  });
}

function renderMatches(matches, options = {}) {
  const container = document.querySelector("#matches");
  if (!container) return;

  const selectable = options.selectable !== false;
  const filtered = options.filterTeacher
    ? matches.filter(match => (match.teacher_name || "").toLowerCase().includes(options.filterTeacher.toLowerCase()))
    : matches;

  container.innerHTML = filtered.map(match => {
    const selected = appState.selectedMatchId === match.id ? "selected" : "";
    const tag = selectable ? "button" : "div";
    const attrs = selectable
      ? `class="record secondary ${selected}" data-match-id="${escapeAttribute(match.id)}" type="button"`
      : `class="record ${selected}"`;

    return `
      <${tag} ${attrs}>
        <div class="row">
          <h3>${displayText(match.id)} ${displayText(match.parent_name)}</h3>
          <span class="pill amber">${displayText(match.status, "teacher_contacted")}</span>
        </div>
        <div class="muted">${displayText(match.student_name, "Student")} / ${displayText(match.teacher_name, "Teacher")} / ${displayText(match.subject, "subject")}</div>
        <div class="muted">${displayText(match.next_action)}</div>
        <div class="muted" style="font-size: 0.8em; text-align: right; margin-top: 4px;">Matched: ${formatDate(match.created_at)}</div>
        ${(localStorage.getItem("role") === "admin" || localStorage.getItem("role") === "developer") ? `<button type="button" style="margin-top:8px; font-size:0.8em;" onclick="event.stopPropagation(); archiveRecord('match', '${escapeAttribute(match.id)}')">Archive</button>` : ""}
      </${tag}>
    `;
  }).join("") || `<div class="record muted">No matches yet.</div>`;

  if (!selectable) return;

  container.querySelectorAll("[data-match-id]").forEach(button => {
    button.addEventListener("click", () => {
      appState.selectedMatchId = button.dataset.matchId;
      if (typeof options.onSelect === "function") {
        options.onSelect();
      }
    });
  });
}

function renderTeachers(teachers, options = {}) {
  const container = document.querySelector("#teachers");
  if (!container) return;

  const filtered = options.filterName
    ? teachers.filter(teacher => (teacher.name || "").toLowerCase().includes(options.filterName.toLowerCase()))
    : teachers;

  container.innerHTML = filtered.map(teacher => {
    const openSlots = Math.max(0, safeNumber(teacher.capacity) - safeNumber(teacher.active_matches));
    return `
      <div class="record">
        <div class="row">
          <h3>${displayText(teacher.name, "Unnamed teacher")}</h3>
          <span class="pill green">${escapeHtml(openSlots)} open</span>
        </div>
        <div class="muted">${textList(teacher.subjects)} / ${textList(teacher.levels)}</div>
        <div class="muted">${textList(teacher.availability)}</div>
        <div class="muted">${displayText(teacher.rate, "Rate not saved")}</div>
        <div class="muted" style="font-size: 0.8em; text-align: right; margin-top: 4px;">Registered: ${formatDate(teacher.created_at)}</div>
        ${(localStorage.getItem("role") === "admin" || localStorage.getItem("role") === "developer") ? `<button type="button" style="margin-top:8px; font-size:0.8em;" onclick="archiveRecord('teacher', '${escapeAttribute(teacher.id)}')">Archive</button>` : ""}
      </div>
    `;
  }).join("") || `<div class="record muted">No teachers yet.</div>`;
}

function renderFollowups(followups) {
  const container = document.querySelector("#followups");
  if (!container) return;

  container.innerHTML = followups.map(item => `
    <div class="record">
      <div class="row">
        <h3>${displayText(item.id)} ${displayText(item.name)}</h3>
        <span class="pill">${displayText(item.type)}</span>
      </div>
      <div class="muted">${displayText(item.status)}</div>
      <div>${displayText(item.next_action)}</div>
    </div>
  `).join("") || `<div class="record muted">No follow-ups due.</div>`;
}

function renderLeaveRequests(leaveRequests, options = {}) {
  const container = document.querySelector("#leaveRequests");
  if (!container) return;

  const selectable = options.selectable !== false;
  const filtered = options.filterTeacher
    ? leaveRequests.filter(req => (req.teacher_name || "").toLowerCase().includes(options.filterTeacher.toLowerCase()))
    : leaveRequests;

  container.innerHTML = filtered.map(request => {
    const selected = appState.selectedLeaveId === request.id ? "selected" : "";
    const tag = selectable ? "button" : "div";
    const attrs = selectable
      ? `class="record secondary ${selected}" data-leave-id="${escapeAttribute(request.id)}" type="button"`
      : `class="record ${selected}"`;

    return `
      <${tag} ${attrs}>
        <div class="row">
          <h3>${displayText(request.id)} ${displayText(request.student_name, "Student")}</h3>
          <span class="pill ${request.google_doc_updated ? "green" : "amber"}">${request.google_doc_updated ? "doc updated" : "doc needed"}</span>
        </div>
        <div class="muted">${displayText(request.teacher_name, "Teacher open")} / ${displayText(request.subject, "class")} / ${displayText(request.class_date, "date open")}</div>
        <div>${displayText(request.next_action)}</div>
        <div class="muted" style="font-size: 0.8em; text-align: right; margin-top: 4px;">Requested: ${formatDate(request.created_at)}</div>
      </${tag}>
    `;
  }).join("") || `<div class="record muted">No leave requests yet.</div>`;

  if (!selectable) return;

  container.querySelectorAll("[data-leave-id]").forEach(button => {
    button.addEventListener("click", () => {
      appState.selectedLeaveId = button.dataset.leaveId;
      const request = appState.data.leave_requests.find(item => item.id === appState.selectedLeaveId);
      const label = document.querySelector("#selectedLeaveLabel");
      if (label) {
        label.textContent = request ? request.id : "No leave selected";
      }
      if (typeof options.onSelect === "function") {
        options.onSelect();
      }
    });
  });
}

function renderCandidates(candidates = [], onCreateMatch) {
  const container = document.querySelector("#matchCandidates");
  if (!container) return;

  container.innerHTML = candidates.map(candidate => `
    <div class="record">
      <div class="row">
        <h3>${displayText(candidate.teacher_name, "Unnamed teacher")}</h3>
        <span class="pill green">Score ${displayText(candidate.score, 0)}</span>
      </div>
      <div class="muted">${displayText(candidate.rate, "No rate saved")}</div>
      <div>${candidate.reasons && candidate.reasons.length ? textList(candidate.reasons) : "No strong fit reasons."}</div>
      <div class="muted">${textList(candidate.cautions)}</div>
      <button type="button" data-create-match="${escapeAttribute(candidate.teacher_id)}">Create Match</button>
    </div>
  `).join("") || `<div class="record muted">No candidates loaded.</div>`;

  container.querySelectorAll("[data-create-match]").forEach(button => {
    button.addEventListener("click", () => onCreateMatch(button.dataset.createMatch));
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const role = localStorage.getItem("role");
  const token = localStorage.getItem("token");
  
  const nav = document.querySelector(".site-nav");
  if (nav) {
    if (role !== "admin" && role !== "developer") {
      const adminLink = nav.querySelector('a[href="/admin.html"]');
      if (adminLink) adminLink.style.display = "none";
    }
    if (role === "parent") {
      const teacherLink = nav.querySelector('a[href="/teachers.html"]');
      if (teacherLink) teacherLink.style.display = "none";
    }
    if (token) {
      const logoutBtn = document.createElement("a");
      logoutBtn.href = "#";
      logoutBtn.textContent = "Logout";
      logoutBtn.style.float = "right";
      logoutBtn.addEventListener("click", (e) => {
        e.preventDefault();
        localStorage.removeItem("token");
        localStorage.removeItem("role");
        window.location.href = "/login.html";
      });
      nav.appendChild(logoutBtn);
    }
  }
});

/* ---------------------------------------------------
   DEV TOOLS WIDGET
--------------------------------------------------- */
function initDevTools() {
  const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  if (!isLocalhost) return;

  const widget = document.createElement('div');
  widget.id = 'dev-tools-widget';
  widget.className = 'collapsed';
  
  widget.innerHTML = `
    <div id="dev-tools-header">
      <span>🛠️ Dev Tools</span>
      <span id="dev-tools-toggle" style="font-size:16px;">▲</span>
    </div>
    <hr />
    <div style="font-size:11px; color:var(--muted); text-transform:uppercase;">Impersonate</div>
    <div class="dev-btn-group">
      <button class="secondary" id="dev-imp-admin">Admin</button>
      <button class="secondary" id="dev-imp-teacher">Teacher</button>
      <button class="secondary" id="dev-imp-parent">Parent</button>
    </div>
    <hr />
    <div style="font-size:11px; color:var(--muted); text-transform:uppercase;">State & DB</div>
    <button class="secondary" id="dev-fill-data">✨ Fill Mock Data</button>
    <button style="background:var(--danger);" id="dev-nuke-seed">⚠️ Nuke & Seed DB</button>
  `;

  document.body.appendChild(widget);

  // Toggle Collapse
  document.getElementById('dev-tools-header').addEventListener('click', () => {
    const isCollapsed = widget.classList.toggle('collapsed');
    document.getElementById('dev-tools-toggle').textContent = isCollapsed ? '▲' : '▼';
  });

  // Impersonate Function
  async function impersonate(role) {
    try {
      const res = await fetch(`/api/dev/impersonate?role=${role}`, { method: 'POST' });
      if (!res.ok) throw new Error("Impersonation failed");
      const data = await res.json();
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("role", data.role);
      
      // Redirect based on role
      if (role === 'admin') window.location.href = '/admin.html';
      else if (role === 'teacher') window.location.href = '/teachers.html';
      else window.location.href = '/parents.html';
      
    } catch (e) {
      alert(e.message);
    }
  }

  document.getElementById('dev-imp-admin').addEventListener('click', () => impersonate('admin'));
  document.getElementById('dev-imp-teacher').addEventListener('click', () => impersonate('teacher'));
  document.getElementById('dev-imp-parent').addEventListener('click', () => impersonate('parent'));

  // Nuke & Seed Function
  document.getElementById('dev-nuke-seed').addEventListener('click', async () => {
    if (!confirm("Are you sure? This will wipe the database and re-seed it!")) return;
    try {
      const res = await fetch('/api/dev/nuke-and-seed', { method: 'POST' });
      if (!res.ok) throw new Error("Failed to nuke and seed");
      alert("Database nuked and seeded! Refreshing...");
      window.location.reload();
    } catch (e) {
      alert(e.message);
    }
  });

  // Fill Mock Data Function
  document.getElementById('dev-fill-data').addEventListener('click', () => {
    const mockData = {
      name: "Mock Dev User",
      parent_name: "Mock Parent",
      student_name: "Mock Student",
      email: "mock_" + Math.floor(Math.random()*1000) + "@example.com",
      password: "password",
      subjects: "Math, Physics",
      levels: "High School, AP",
      availability: "Monday 5pm, Thursday 6pm",
      rate: "$60/hr",
      contact: "mock@example.com / 555-0101",
      subject: "Math",
      level: "High School",
      frequency: "Twice a week",
      raw_message: "This is a mock message automatically filled by dev tools. I am looking for a tutor for my child.",
      reason: "Sick leave",
      class_date: "Next Tuesday 5pm"
    };

    document.querySelectorAll('input:not([type="hidden"]), textarea').forEach(input => {
      const name = input.name || input.id;
      if (!name) return;
      
      let matchedKey = Object.keys(mockData).find(k => name.toLowerCase().includes(k.toLowerCase()));
      if (matchedKey) {
        input.value = mockData[matchedKey];
      }
    });
    
    // Attempt to select an option for selects
    document.querySelectorAll('select').forEach(select => {
      if (select.options.length > 1) {
        select.selectedIndex = 1;
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", initDevTools);

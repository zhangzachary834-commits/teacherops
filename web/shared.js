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

/* ---------------------------------------------------
   NAME SANITIZATION & AUTO-FILL HELPER
--------------------------------------------------- */
function cleanName(rawName) {
  if (!rawName) return "";
  let name = String(rawName).trim();
  // Strip leading/trailing role labels like "Parent", "Student", "Teacher", "User"
  name = name.replace(/^(parent|student|teacher|user)\s+/i, "");
  name = name.replace(/\s+(parent|student|teacher|user)$/i, "");
  return name.trim();
}

function autoFillForms(data) {
  if (!data) return;
  
  const role = data.role || localStorage.getItem("role") || "";
  const profile = data.user_profile || {};
  
  // 1. Resolve Parent and Student Name (clean, without role labels)
  let parentName = cleanName(profile.parent_name || "");
  let studentName = cleanName(profile.student_name || "");
  
  if (!parentName || !studentName) {
    if (data.inquiries && data.inquiries.length > 0) {
      const inq = data.inquiries[0];
      if (!parentName && inq.parent_name) parentName = cleanName(inq.parent_name);
      if (!studentName && inq.student_name) studentName = cleanName(inq.student_name);
    }
  }

  if (!parentName) parentName = cleanName(localStorage.getItem("saved_parent_name") || "");
  if (!studentName) studentName = cleanName(localStorage.getItem("saved_student_name") || "");

  // Auto-fill New Inquiry Form (#inquiryForm on parents.html)
  const inquiryForm = document.querySelector("#inquiryForm");
  if (inquiryForm) {
    const parentInput = inquiryForm.querySelector("input[name='parent_name']");
    const studentInput = inquiryForm.querySelector("input[name='student_name']");
    
    if (parentInput) {
      const currentVal = cleanName(parentInput.value.trim());
      if (!currentVal || currentVal.toLowerCase() === "wang" || currentVal.toLowerCase() === "parent wang" || parentInput.dataset.autofilled === "true") {
        if (parentName) {
          parentInput.value = cleanName(parentName);
          parentInput.dataset.autofilled = "true";
        }
      }
    }
    
    if (studentInput) {
      const currentVal = cleanName(studentInput.value.trim());
      if (!currentVal || currentVal.toLowerCase() === "eric" || currentVal.toLowerCase() === "student eric" || studentInput.dataset.autofilled === "true") {
        if (studentName) {
          studentInput.value = cleanName(studentName);
          studentInput.dataset.autofilled = "true";
        }
      }
    }
  }

  // Update Leave Request Form (#leaveForm) placeholder if student name is known
  const leaveInput = document.querySelector("#leaveForm textarea[name='raw_message']");
  if (leaveInput && studentName) {
    leaveInput.placeholder = `Example: ${cleanName(studentName)} needs to take leave this Friday because of travel.`;
  }

  // 2. Resolve Teacher Name & Profile
  let teacherName = cleanName(profile.name || "");
  if (!teacherName && data.teachers && data.teachers.length > 0 && role === "teacher") {
    teacherName = cleanName(data.teachers[0].name || "");
  }
  if (!teacherName) teacherName = cleanName(localStorage.getItem("saved_teacher_name") || "");

  const teacherForm = document.querySelector("#teacherForm");
  if (teacherForm && teacherName && (role === "teacher" || !role)) {
    const nameInput = teacherForm.querySelector("input[name='name']");
    if (nameInput) {
      const currentVal = cleanName(nameInput.value.trim());
      if (!currentVal || nameInput.dataset.autofilled === "true") {
        nameInput.value = cleanName(teacherName);
        nameInput.dataset.autofilled = "true";
        
        const teacher = data.teachers && data.teachers.find(t => cleanName(t.name || "").toLowerCase() === teacherName.toLowerCase());
        if (teacher) {
          if (teacherForm.elements["subjects"] && !teacherForm.elements["subjects"].value) {
            teacherForm.elements["subjects"].value = teacher.subjects ? (Array.isArray(teacher.subjects) ? teacher.subjects.join("; ") : teacher.subjects) : "";
          }
          if (teacherForm.elements["levels"] && !teacherForm.elements["levels"].value) {
            teacherForm.elements["levels"].value = teacher.levels ? (Array.isArray(teacher.levels) ? teacher.levels.join("; ") : teacher.levels) : "";
          }
          if (teacherForm.elements["availability"] && !teacherForm.elements["availability"].value) {
            teacherForm.elements["availability"].value = teacher.availability ? (Array.isArray(teacher.availability) ? teacher.availability.join("; ") : teacher.availability) : "";
          }
          if (teacherForm.elements["rate"] && !teacherForm.elements["rate"].value) {
            teacherForm.elements["rate"].value = teacher.rate || "";
          }
          if (teacherForm.elements["capacity"] && teacherForm.elements["capacity"].value === "1" && teacher.capacity) {
            teacherForm.elements["capacity"].value = teacher.capacity;
          }
        }
      }
    }
  }

  const teacherFilter = document.querySelector("#teacherFilter");
  if (teacherFilter && teacherName && !teacherFilter.value) {
    teacherFilter.value = cleanName(teacherName);
    if (typeof window.renderPage === "function") {
      window.renderPage();
    }
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
  
  autoFillForms(appState.data);
  return appState.data;
}

async function submitJson(form, path, successText, onSuccess) {
  try {
    const formValues = formData(form);
    if (formValues.parent_name) localStorage.setItem("saved_parent_name", cleanName(formValues.parent_name));
    if (formValues.student_name) localStorage.setItem("saved_student_name", cleanName(formValues.student_name));
    if (formValues.name) localStorage.setItem("saved_teacher_name", cleanName(formValues.name));

    await api(path, {
      method: "POST",
      body: JSON.stringify(formValues)
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
        localStorage.removeItem("saved_parent_name");
        localStorage.removeItem("saved_student_name");
        localStorage.removeItem("saved_teacher_name");
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
    <div class="dev-tools-content">
      <hr />
      <div class="dev-group-title">👑 Admin Test Accounts</div>
      <div class="dev-btn-group">
        <button class="secondary" data-dev-acc="admin" title="dev_admin@example.com">Admin (Main)</button>
        <button class="secondary" data-dev-acc="admin2" title="dev_admin2@example.com">Admin (Ops)</button>
      </div>

      <div class="dev-group-title">👨‍👩‍👧 Parent Test Accounts</div>
      <div class="dev-btn-group">
        <button class="secondary" data-dev-acc="parent_carol" title="Carol (George's Mom)">Parent Carol</button>
        <button class="secondary" data-dev-acc="parent_wang" title="Wang (Eric's Dad)">Parent Wang</button>
      </div>

      <div class="dev-group-title">🎓 Student Test Accounts</div>
      <div class="dev-btn-group">
        <button class="secondary" data-dev-acc="student_dave" title="George (High School Math)">Student George</button>
        <button class="secondary" data-dev-acc="student_eric" title="Eric (Grade 8 Math)">Student Eric</button>
      </div>

      <div class="dev-group-title">📚 Teacher Test Accounts</div>
      <div class="dev-btn-group">
        <button class="secondary" data-dev-acc="teacher_alice" title="Alice Chen (Math/Physics)">Teacher Alice</button>
        <button class="secondary" data-dev-acc="teacher_bob" title="Bob Smith (English)">Teacher Bob</button>
      </div>

      <hr />
      <div class="dev-group-title">State & DB</div>
      <button class="secondary" id="dev-fill-data">✨ Fill Mock Form</button>
      <button class="secondary" id="dev-restart-server">🔄 Restart Server</button>
      <button style="background:var(--danger);" id="dev-nuke-seed">⚠️ Nuke & Seed DB</button>
    </div>
  `;

  document.body.appendChild(widget);

  // Toggle Collapse
  document.getElementById('dev-tools-header').addEventListener('click', () => {
    const isCollapsed = widget.classList.toggle('collapsed');
    document.getElementById('dev-tools-toggle').textContent = isCollapsed ? '▲' : '▼';
  });

  // Test Account Switcher / Impersonator
  async function impersonate(accountId) {
    try {
      const res = await fetch(`/api/dev/impersonate?account_id=${encodeURIComponent(accountId)}`, { method: 'POST' });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Impersonation failed");
      }
      const data = await res.json();
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("role", data.role);
      
      // Redirect based on role
      if (data.role === 'admin' || data.role === 'developer') {
        window.location.href = '/admin.html';
      } else if (data.role === 'teacher') {
        window.location.href = '/teachers.html';
      } else {
        window.location.href = '/parents.html';
      }
    } catch (e) {
      alert("Dev login failed: " + e.message);
    }
  }

  // Attach event listeners to all dev account buttons
  widget.querySelectorAll('[data-dev-acc]').forEach(button => {
    button.addEventListener('click', () => {
      impersonate(button.dataset.devAcc);
    });
  });

  // Restart Server Function
  document.getElementById('dev-restart-server').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/dev/restart', { method: 'POST' });
      if (!res.ok) throw new Error("Failed to restart server");
      setStatus("Server reloading...");
      setTimeout(() => {
        window.location.reload();
      }, 700);
    } catch (e) {
      alert("Restart error: " + e.message);
    }
  });

  // Nuke & Seed Function
  document.getElementById('dev-nuke-seed').addEventListener('click', async () => {
    if (!confirm("Are you sure? This will wipe the database and re-seed with clean dummy test data!")) return;
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

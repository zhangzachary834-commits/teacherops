// Shared by local FastAPI and the static GitHub Pages frontend.
// Set this to a public backend origin later (for example https://api.example.com).
window.TEACHEROPS_API_BASE = window.TEACHEROPS_API_BASE || "";

window.teacherOpsApiUrl = function teacherOpsApiUrl(path) {
  const base = String(window.TEACHEROPS_API_BASE || "").replace(/\/$/, "");
  const normalizedPath = String(path || "").startsWith("/") ? String(path) : "/" + String(path || "");

  if (!base && window.location.hostname.endsWith("github.io")) {
    throw new Error(
      "TeacherOps frontend is live, but its Python backend is not deployed publicly yet."
    );
  }

  return base + normalizedPath;
};

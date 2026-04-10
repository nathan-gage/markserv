(() => {
  const WIDTH_KEY = "markserv-sidebar-width";
  const COLLAPSED_KEY = "markserv-sidebar-collapsed";
  const MIN_WIDTH = 180;
  const MAX_WIDTH = 500;
  const DEFAULT_WIDTH = 260;

  function storedWidth() {
    try {
      const v = parseInt(localStorage.getItem(WIDTH_KEY), 10);
      return v >= MIN_WIDTH && v <= MAX_WIDTH ? v : null;
    } catch {
      return null;
    }
  }

  function storedCollapsed() {
    try {
      return localStorage.getItem(COLLAPSED_KEY) === "1";
    } catch {
      return false;
    }
  }

  function applyWidth(px) {
    document.documentElement.style.setProperty("--sidebar-width", px + "px");
  }

  function applyCollapsed(collapsed) {
    document.documentElement.classList.toggle("sidebar-collapsed", collapsed);
  }

  function applySidebarState() {
    const collapsed = storedCollapsed();
    applyCollapsed(collapsed);
    if (!collapsed) {
      applyWidth(storedWidth() ?? DEFAULT_WIDTH);
    }
  }

  // Apply immediately to avoid flash.
  applySidebarState();

  document.addEventListener("DOMContentLoaded", applySidebarState);
  document.addEventListener("htmx:afterSwap", applySidebarState);

  // Collapse toggle — CSS transitions handle the animation.
  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-sidebar-toggle]")) return;
    const next = !storedCollapsed();
    try {
      localStorage.setItem(COLLAPSED_KEY, next ? "1" : "0");
    } catch {}
    applyCollapsed(next);
    if (!next) applyWidth(storedWidth() ?? DEFAULT_WIDTH);
  });

  // Resize drag.
  document.addEventListener("mousedown", (e) => {
    if (!e.target.closest(".sidebar-resize")) return;
    e.preventDefault();
    const sidebar = document.querySelector(".sidebar");
    if (!sidebar) return;

    const startX = e.clientX;
    const startW = sidebar.offsetWidth;
    document.documentElement.classList.add("sidebar-resizing");

    function onMove(ev) {
      const w = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startW + ev.clientX - startX));
      applyWidth(w);
    }

    function onUp(ev) {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.documentElement.classList.remove("sidebar-resizing");
      const w = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startW + ev.clientX - startX));
      try {
        localStorage.setItem(WIDTH_KEY, String(w));
      } catch {}
    }

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  });
})();

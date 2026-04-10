(() => {
  const WIDTH_KEY = "markserv-sidebar-width";
  const PAGE_SHELL = "#page-shell";
  const COLLAPSED_KEY = "markserv-sidebar-collapsed";
  const FOLDER_STATE_KEY = "markserv-folder-states";
  const MIN_WIDTH = 180;
  const MAX_WIDTH = 500;
  const DEFAULT_WIDTH = 260;
  const ANIMATION_MS = 380;

  let animationTimer = null;
  let restoringFolders = false;

  function isPageShellTarget(target) {
    return target instanceof Element && target.matches(PAGE_SHELL);
  }

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

  function beginSidebarAnimation() {
    document.documentElement.classList.add("sidebar-animating");
    if (animationTimer) clearTimeout(animationTimer);
    animationTimer = setTimeout(() => {
      document.documentElement.classList.remove("sidebar-animating");
      animationTimer = null;
    }, ANIMATION_MS);
  }

  // --- Folder toggle persistence ---

  function savedFolderStates() {
    try {
      return JSON.parse(localStorage.getItem(FOLDER_STATE_KEY)) || {};
    } catch {
      return {};
    }
  }

  function saveFolderState(path, open) {
    try {
      const states = savedFolderStates();
      states[path] = open;
      localStorage.setItem(FOLDER_STATE_KEY, JSON.stringify(states));
    } catch {}
  }

  function restoreFolderStates() {
    const saved = savedFolderStates();
    restoringFolders = true;
    document.querySelectorAll(".nav-folder[data-path]").forEach((folder) => {
      const path = folder.dataset.path;
      const serverOpen = folder.open;
      if (serverOpen) {
        // Server marked this open (contains active page) — always keep open.
        return;
      }
      if (path in saved) {
        folder.open = saved[path];
      }
    });
    restoringFolders = false;
  }

  // Save toggle state when user opens/closes a folder.
  document.addEventListener(
    "toggle",
    (e) => {
      if (restoringFolders) return;
      const folder = e.target;
      if (folder.classList?.contains("nav-folder") && folder.dataset.path) {
        saveFolderState(folder.dataset.path, folder.open);
      }
    },
    true,
  );

  // Apply immediately to avoid flash.
  applySidebarState();

  document.addEventListener("DOMContentLoaded", () => {
    applySidebarState();
    restoreFolderStates();
  });
  document.addEventListener("htmx:afterSwap", (event) => {
    if (isPageShellTarget(event.target)) {
      applySidebarState();
      restoreFolderStates();
    }
  });

  // Collapse toggle — CSS transitions handle the animation.
  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-sidebar-toggle]")) return;
    const next = !storedCollapsed();
    beginSidebarAnimation();
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

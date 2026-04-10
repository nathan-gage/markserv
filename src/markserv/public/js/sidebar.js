(() => {
  const WIDTH_KEY = "markserv-sidebar-width";
  const FRAME_SELECTOR = ".sidebar-frame";
  const HANDLE_SELECTOR = ".sidebar-resize";
  const MIN_WIDTH = 180;
  const MAX_WIDTH = 500;
  const DEFAULT_WIDTH = 260;

  function storedWidth() {
    try {
      const value = Number.parseInt(window.localStorage.getItem(WIDTH_KEY) || "", 10);
      return Number.isFinite(value) && value >= MIN_WIDTH && value <= MAX_WIDTH ? value : null;
    } catch {
      return null;
    }
  }

  function applyWidth(px) {
    document.documentElement.style.setProperty("--sidebar-width", `${px}px`);
  }

  function clampWidth(px) {
    return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, px));
  }

  applyWidth(storedWidth() ?? DEFAULT_WIDTH);

  function currentFrame() {
    return document.querySelector(FRAME_SELECTOR);
  }

  document.addEventListener("pointerdown", (event) => {
    if (!event.target.closest(HANDLE_SELECTOR)) {
      return;
    }

    const frame = currentFrame();
    if (!(frame instanceof HTMLElement)) {
      return;
    }

    event.preventDefault();

    const startX = event.clientX;
    const startWidth = frame.getBoundingClientRect().width;
    document.documentElement.classList.add("sidebar-resizing");

    function onMove(moveEvent) {
      applyWidth(clampWidth(startWidth + moveEvent.clientX - startX));
    }

    function onUp(upEvent) {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      document.removeEventListener("pointercancel", onUp);
      document.documentElement.classList.remove("sidebar-resizing");

      const width = clampWidth(startWidth + upEvent.clientX - startX);
      applyWidth(width);
      try {
        window.localStorage.setItem(WIDTH_KEY, String(width));
      } catch {
        // Ignore storage failures.
      }
    }

    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
    document.addEventListener("pointercancel", onUp);
  });
})();

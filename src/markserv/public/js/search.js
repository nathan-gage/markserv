(() => {
  const DIALOG = "[data-search-dialog]";
  const INPUT = "[data-search-input]";
  const RESULTS = "[data-search-results]";
  const SHORTCUT = "[data-search-shortcut]";
  const RESULT = ".search-result";

  const isMac = /mac|iphone|ipad/i.test(
    navigator.userAgentData?.platform || navigator.platform || ""
  );

  function syncLabels() {
    document.querySelectorAll(SHORTCUT).forEach((el) => {
      el.textContent = isMac ? "\u2318K" : "Ctrl K";
    });
  }

  function dialog() {
    return document.querySelector(DIALOG);
  }

  // Cmd/Ctrl+K → toggle
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === "k") {
      e.preventDefault();
      const d = dialog();
      if (!d) return;
      if (d.open) {
        d.close();
      } else {
        d.showModal();
        const input = d.querySelector(INPUT);
        if (input) {
          input.focus();
          input.select();
        }
      }
    }
  });

  // Click trigger button → open
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-search-open]")) {
      e.preventDefault();
      const d = dialog();
      if (d && !d.open) {
        d.showModal();
        const input = d.querySelector(INPUT);
        if (input) {
          input.focus();
          input.select();
        }
      }
    }
  });

  // Backdrop click → close (clicks on dialog itself, outside the modal div)
  document.addEventListener("click", (e) => {
    const d = dialog();
    if (e.target === d) d.close();
  });

  // Arrow keys + Enter inside open dialog
  document.addEventListener("keydown", (e) => {
    const d = dialog();
    if (!d?.open) return;

    const container = d.querySelector(RESULTS);
    if (!container) return;
    const results = [...container.querySelectorAll(RESULT)];
    if (!results.length) return;

    const active = container.querySelector(`${RESULT}.is-active`);
    let idx = active ? results.indexOf(active) : 0;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      idx = (idx + 1) % results.length;
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      idx = (idx - 1 + results.length) % results.length;
    } else if (e.key === "Enter" && idx >= 0 && results[idx]) {
      e.preventDefault();
      results[idx].click();
      return;
    } else {
      return;
    }

    results.forEach((r) => r.classList.remove("is-active"));
    results[idx].classList.add("is-active");
    results[idx].scrollIntoView({ block: "nearest" });
  });

  // Mouse hover → update active
  document.addEventListener("mouseenter", (e) => {
    const result = e.target.closest?.(RESULT);
    if (!result) return;
    const container = result.closest(RESULTS);
    if (!container) return;
    container.querySelectorAll(RESULT).forEach((r) => r.classList.remove("is-active"));
    result.classList.add("is-active");
  }, true);

  // After HTMX swaps results, clear stale is-active (CSS :first-child takes over)
  document.addEventListener("htmx:afterSwap", (e) => {
    if (e.target.matches?.(RESULTS)) {
      e.target.querySelectorAll(`${RESULT}.is-active`).forEach((r) => {
        r.classList.remove("is-active");
      });
    }
    syncLabels();
  });

  // Init
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncLabels, { once: true });
  } else {
    syncLabels();
  }
})();

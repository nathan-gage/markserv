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

  function transition(update) {
    if (document.startViewTransition) {
      document.startViewTransition(update);
    } else {
      update();
    }
  }

  function openSearch(d) {
    if (!d || d.open) return;
    transition(() => d.showModal());
    requestAnimationFrame(() => {
      const input = d.querySelector(INPUT);
      if (input) {
        input.focus();
        input.select();
      }
    });
  }

  function closeSearch(d) {
    if (!d || !d.open) return;
    transition(() => d.close());
  }

  // Cmd/Ctrl+K toggle + Escape
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === "k") {
      e.preventDefault();
      const d = dialog();
      if (d?.open) closeSearch(d);
      else openSearch(d);
      return;
    }

    if (e.key === "Escape") {
      const d = dialog();
      if (d?.open) {
        e.preventDefault();
        closeSearch(d);
      }
    }
  });

  // Trigger button
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-search-open]")) {
      e.preventDefault();
      openSearch(dialog());
    }
  });

  // Close button
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-search-close]")) {
      e.preventDefault();
      closeSearch(dialog());
    }
  });

  // Backdrop click
  document.addEventListener("click", (e) => {
    const d = dialog();
    if (e.target === d) closeSearch(d);
  });

  // Arrow keys + Enter
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

  // Mouse hover
  document.addEventListener("mouseenter", (e) => {
    const result = e.target.closest?.(RESULT);
    if (!result) return;
    const container = result.closest(RESULTS);
    if (!container) return;
    container.querySelectorAll(RESULT).forEach((r) => r.classList.remove("is-active"));
    result.classList.add("is-active");
  }, true);

  // HTMX swap: clear stale is-active
  document.addEventListener("htmx:afterSwap", (e) => {
    if (e.target.matches?.(RESULTS)) {
      e.target.querySelectorAll(`${RESULT}.is-active`).forEach((r) => {
        r.classList.remove("is-active");
      });
    }
    syncLabels();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncLabels, { once: true });
  } else {
    syncLabels();
  }
})();

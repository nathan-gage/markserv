(() => {
  const DIALOG = "[data-search-dialog]";
  const INPUT = "[data-search-input]";
  const RESULTS = "[data-search-results]";
  const SHORTCUT = "[data-search-shortcut]";
  const RESULT = ".search-result";
  const PAGE_SHELL = "#page-shell";
  const EMPTY_STATE = '<p class="search-state">Start typing to search pages, headings, and content.</p>';

  let pageRequestInFlight = false;
  let pendingOpenAfterSwap = false;
  let activeTransition = null;

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

  function clearActive(container) {
    container?.querySelectorAll(`${RESULT}.is-active`).forEach((r) => {
      r.classList.remove("is-active");
    });
  }

  function transition(root, update) {
    const run =
      typeof root?.startViewTransition === "function"
        ? () => root.startViewTransition({ callback: update })
        : typeof document.startViewTransition === "function"
          ? () => document.startViewTransition(update)
          : null;

    if (!run || pageRequestInFlight || activeTransition) {
      update();
      return null;
    }

    try {
      const viewTransition = run();
      if (viewTransition?.finished?.finally) {
        activeTransition = viewTransition;
        viewTransition.finished.finally(() => {
          if (activeTransition === viewTransition) {
            activeTransition = null;
          }
        });
      }
      return viewTransition;
    } catch {
      update();
      return null;
    }
  }

  function resetSearch(d, { clearQuery = false } = {}) {
    if (!d) return;

    const input = d.querySelector(INPUT);
    const container = d.querySelector(RESULTS);

    if (clearQuery && input) {
      input.value = "";
    }

    clearActive(container);

    if (clearQuery && container) {
      container.innerHTML = EMPTY_STATE;
    }
  }

  function focusSearchInput(d) {
    requestAnimationFrame(() => {
      const input = d?.querySelector(INPUT);
      if (input) {
        input.focus();
        input.select();
      }
    });
  }

  function openSearch(d) {
    if (!d || d.open) return;
    if (pageRequestInFlight) {
      pendingOpenAfterSwap = true;
      return;
    }
    pendingOpenAfterSwap = false;
    transition(d, () => d.showModal());
    focusSearchInput(d);
  }

  function closeSearch(d, { clearQuery = false, animate = true } = {}) {
    if (!d) return;
    pendingOpenAfterSwap = false;
    if (d.open) {
      if (animate) transition(d, () => d.close());
      else d.close();
    }
    resetSearch(d, { clearQuery });
  }

  function isModifiedNavigation(event) {
    return event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
  }

  function isPageShellTarget(target) {
    return target instanceof Element && target.matches(PAGE_SHELL);
  }

  function isPageShellNavigationTarget(target) {
    const link = target instanceof Element ? target.closest("a") : null;
    if (!link) return false;
    return (link.getAttribute("hx-target") || link.getAttribute("data-hx-target")) === PAGE_SHELL;
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

  document.addEventListener(
    "pointerdown",
    (e) => {
      if (e.target.closest?.(RESULT) || isPageShellNavigationTarget(e.target)) {
        closeSearch(dialog(), { clearQuery: true, animate: false });
      }
    },
    true
  );

  document.addEventListener("click", (e) => {
    const result = e.target.closest?.(RESULT);
    if (result) {
      if (!isModifiedNavigation(e)) {
        closeSearch(dialog(), { clearQuery: true, animate: false });
      }
      return;
    }

    if (e.target.closest("[data-search-open]")) {
      e.preventDefault();
      openSearch(dialog());
      return;
    }

    if (e.target.closest("[data-search-close]")) {
      e.preventDefault();
      closeSearch(dialog());
      return;
    }

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

    clearActive(container);
    results[idx].classList.add("is-active");
    results[idx].scrollIntoView({ block: "nearest" });
  });

  // Mouse hover
  document.addEventListener(
    "mouseenter",
    (e) => {
      const result = e.target.closest?.(RESULT);
      if (!result) return;
      const container = result.closest(RESULTS);
      if (!container) return;
      clearActive(container);
      result.classList.add("is-active");
    },
    true
  );

  document.addEventListener("htmx:beforeRequest", (e) => {
    const target = e.detail?.target;
    if (isPageShellTarget(target)) {
      pageRequestInFlight = true;
      closeSearch(dialog(), { clearQuery: true, animate: false });
    }
  });

  document.addEventListener("htmx:afterRequest", (e) => {
    if (isPageShellTarget(e.detail?.target)) {
      pageRequestInFlight = false;
    }
  });

  document.addEventListener("htmx:responseError", (e) => {
    if (isPageShellTarget(e.detail?.target)) {
      pageRequestInFlight = false;
    }
  });

  document.addEventListener("htmx:sendAbort", (e) => {
    if (isPageShellTarget(e.detail?.target)) {
      pageRequestInFlight = false;
    }
  });

  document.addEventListener("htmx:beforeHistorySave", () => {
    closeSearch(dialog(), { clearQuery: true, animate: false });
  });

  document.addEventListener("htmx:historyRestore", () => {
    closeSearch(dialog(), { clearQuery: true, animate: false });
  });

  // HTMX swap: clear stale is-active
  document.addEventListener("htmx:afterSwap", (e) => {
    if (e.target.matches?.(RESULTS)) {
      clearActive(e.target);
    }

    if (isPageShellTarget(e.target)) {
      pageRequestInFlight = false;
      if (pendingOpenAfterSwap) {
        const d = dialog();
        pendingOpenAfterSwap = false;
        if (d && !d.open) {
          d.showModal();
          focusSearchInput(d);
        }
      }
    }

    syncLabels();
  });

  window.addEventListener("pagehide", () => {
    closeSearch(dialog(), { clearQuery: true, animate: false });
  });

  window.addEventListener("pageshow", (e) => {
    if (e.persisted) {
      closeSearch(dialog(), { clearQuery: true, animate: false });
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncLabels, { once: true });
  } else {
    syncLabels();
  }
})();

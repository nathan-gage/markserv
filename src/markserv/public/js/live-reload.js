(() => {
  const PAGE_SHELL = "#page-shell";

  let source = null;
  let reloadRequest = null;

  function isPageShellTarget(target) {
    return target instanceof Element && target.matches(PAGE_SHELL);
  }

  function currentPageHref() {
    if (!(document.getElementById("page-shell") instanceof HTMLElement)) {
      return null;
    }

    const { pathname, search } = window.location;
    return `${pathname}${search}`;
  }

  function closeSource() {
    if (!source) return;
    source.close();
    source = null;
  }

  function syncSource() {
    if (!currentPageHref()) {
      closeSource();
      return;
    }

    if (source) return;

    source = new EventSource("/_events");
    source.addEventListener("reload", requestReload);
    source.addEventListener("error", () => {
      if (source && source.readyState === EventSource.CLOSED) {
        source = null;
      }
    });
  }

  function requestReload() {
    const pageHref = currentPageHref();
    if (!pageHref || reloadRequest || !window.htmx) {
      return;
    }

    reloadRequest = window.htmx.ajax("GET", pageHref, {
      target: "#page-shell",
      swap: "outerHTML",
    });

    if (reloadRequest && typeof reloadRequest.finally === "function") {
      reloadRequest.finally(() => {
        reloadRequest = null;
        syncSource();
      });
      return;
    }

    reloadRequest = null;
    syncSource();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncSource, { once: true });
  } else {
    syncSource();
  }

  document.addEventListener("htmx:afterSwap", (event) => {
    if (isPageShellTarget(event.target)) {
      syncSource();
    }
  });
  window.addEventListener("pagehide", closeSource);
  window.addEventListener("beforeunload", closeSource);
})();

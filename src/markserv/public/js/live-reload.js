(() => {
  let source = null;
  let reloadRequest = null;

  function currentLiveFragmentHref() {
    const shell = document.getElementById("page-shell");
    if (!(shell instanceof HTMLElement)) return null;

    const href = shell.dataset.liveFragment;
    return href || null;
  }

  function closeSource() {
    if (!source) return;
    source.close();
    source = null;
  }

  function syncSource() {
    if (!currentLiveFragmentHref()) {
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
    const liveFragmentHref = currentLiveFragmentHref();
    if (!liveFragmentHref || reloadRequest || !window.htmx) {
      return;
    }

    reloadRequest = window.htmx.ajax("GET", liveFragmentHref, {
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

  document.addEventListener("htmx:afterSwap", syncSource);
  window.addEventListener("pagehide", closeSource);
  window.addEventListener("beforeunload", closeSource);
})();

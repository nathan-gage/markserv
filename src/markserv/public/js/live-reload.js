(() => {
  let liveReloadSource = null;

  function trackSource(event) {
    const elt = event.target;
    if (!(elt instanceof Element)) return;
    if (elt.getAttribute("sse-connect") !== "/_events") return;

    const source = event.detail && event.detail.source;
    if (!(source instanceof EventSource)) return;

    if (liveReloadSource && liveReloadSource !== source) {
      liveReloadSource.close();
    }

    liveReloadSource = source;
  }

  function clearTrackedSource(event) {
    const source = event.detail && event.detail.source;
    if (source && source === liveReloadSource) {
      liveReloadSource = null;
    }
  }

  function closeLiveReloadSource() {
    if (!liveReloadSource) return;
    liveReloadSource.close();
    liveReloadSource = null;
  }

  function shouldCloseForClick(event) {
    if (event.defaultPrevented) return false;
    if (event.button !== 0) return false;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;

    const link = event.target.closest("a[href]");
    if (!(link instanceof HTMLAnchorElement)) return false;
    if (link.target && link.target !== "_self") return false;
    if (link.hasAttribute("download")) return false;

    const href = link.getAttribute("href");
    if (!href || href.startsWith("#") || href.startsWith("javascript:")) return false;

    return true;
  }

  document.addEventListener("htmx:sseOpen", trackSource);
  document.addEventListener("htmx:sseClose", clearTrackedSource);
  window.addEventListener("pagehide", closeLiveReloadSource);
  window.addEventListener("beforeunload", closeLiveReloadSource);
  document.addEventListener(
    "click",
    (event) => {
      if (shouldCloseForClick(event)) {
        closeLiveReloadSource();
      }
    },
    true,
  );
})();

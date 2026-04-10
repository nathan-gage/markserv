(() => {
  if (document.documentElement.dataset.devReload !== "true") {
    return;
  }

  let connectedOnce = false;
  let sawDisconnect = false;

  const source = new EventSource("/_dev/reload");

  source.addEventListener("open", () => {
    if (connectedOnce && sawDisconnect) {
      window.location.reload();
      return;
    }

    connectedOnce = true;
    sawDisconnect = false;
  });

  source.addEventListener("error", () => {
    if (connectedOnce) {
      sawDisconnect = true;
    }
  });
})();

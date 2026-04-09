(() => {
  function updateFavicon() {
    const shell = document.getElementById("page-shell");
    if (!shell) return;

    const href = shell.dataset.icon;
    if (!href) return;

    const link = document.getElementById("favicon");
    if (!link || link.getAttribute("href") === href) return;

    // Preload the image, then swap the link only once loaded
    const img = new Image();
    img.onload = () => {
      link.setAttribute("href", href);
    };
    img.src = href;
  }

  // After HTMX swaps in new content, update the favicon
  document.addEventListener("htmx:afterSwap", updateFavicon);

  // Also run on initial load in case the icon hasn't loaded yet
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", updateFavicon);
  } else {
    updateFavicon();
  }
})();

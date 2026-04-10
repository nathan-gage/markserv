(() => {
  const OPEN_SELECTOR = "[data-search-open]";
  const CLOSE_SELECTOR = "[data-search-close]";
  const OVERLAY_SELECTOR = "[data-search-overlay]";
  const INPUT_SELECTOR = "[data-search-input]";
  const RESULTS_SELECTOR = "[data-search-results]";
  const STATE_SELECTOR = "[data-search-state]";
  const SHORTCUT_SELECTOR = "[data-search-shortcut]";
  const SEARCH_ENDPOINT = "/_search";
  const RESULT_LIMIT = 12;
  const SEARCH_DEBOUNCE_MS = 90;

  let searchTimer = null;
  let searchController = null;
  let searchRequestId = 0;
  let selectedIndex = -1;
  let currentResults = [];
  let lastFocusedElement = null;

  function isMacPlatform() {
    const platform = navigator.userAgentData?.platform || navigator.platform || "";
    return /mac|iphone|ipad|ipod/i.test(platform);
  }

  function shortcutLabel() {
    return isMacPlatform() ? "⌘K" : "Ctrl K";
  }

  function syncShortcutLabels() {
    document.querySelectorAll(SHORTCUT_SELECTOR).forEach((element) => {
      element.textContent = shortcutLabel();
    });
  }

  function overlay() {
    return document.querySelector(OVERLAY_SELECTOR);
  }

  function input() {
    return document.querySelector(INPUT_SELECTOR);
  }

  function resultsContainer() {
    return document.querySelector(RESULTS_SELECTOR);
  }

  function stateElement() {
    return document.querySelector(STATE_SELECTOR);
  }

  function isOpen() {
    const element = overlay();
    return !!element && !element.hasAttribute("hidden");
  }

  function setDocumentOpenState(open) {
    document.documentElement.classList.toggle("search-open", open);
    if (document.body) {
      document.body.classList.toggle("search-open", open);
    }
  }

  function setHidden(element, hidden) {
    if (!element) return;
    if (hidden) {
      element.setAttribute("hidden", "hidden");
    } else {
      element.removeAttribute("hidden");
    }
  }

  function abortSearch() {
    if (searchController) {
      searchController.abort();
      searchController = null;
    }
  }

  function clearResults() {
    currentResults = [];
    selectedIndex = -1;
    const container = resultsContainer();
    if (container) {
      container.replaceChildren();
    }
  }

  function setState(message) {
    const element = stateElement();
    if (!element) return;
    element.textContent = message;
    element.hidden = false;
  }

  function hideState() {
    const element = stateElement();
    if (!element) return;
    element.hidden = true;
  }

  function syncActiveResult() {
    const container = resultsContainer();
    if (!container) return;

    container.querySelectorAll(".search-result").forEach((element, index) => {
      const isActive = index === selectedIndex;
      element.classList.toggle("is-active", isActive);
      element.setAttribute("aria-selected", isActive ? "true" : "false");
      if (isActive) {
        element.scrollIntoView({ block: "nearest" });
      }
    });
  }

  function moveSelection(delta) {
    if (!currentResults.length) return;
    selectedIndex = (selectedIndex + delta + currentResults.length) % currentResults.length;
    syncActiveResult();
  }

  function navigateToResult(result) {
    if (!result?.href) return;
    window.location.assign(result.href);
  }

  function buildResultElement(result, index) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "search-result";
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", "false");

    const title = document.createElement("span");
    title.className = "search-result-title";
    title.textContent = result.title;

    const path = document.createElement("span");
    path.className = "search-result-path";
    path.textContent = result.rel_path;

    const header = document.createElement("span");
    header.className = "search-result-header";
    header.append(title, path);
    button.append(header);

    if (result.snippet) {
      const snippet = document.createElement("span");
      snippet.className = "search-result-snippet";
      snippet.textContent = result.snippet;
      button.append(snippet);
    }

    const activate = () => {
      selectedIndex = index;
      syncActiveResult();
    };

    button.addEventListener("mouseenter", activate);
    button.addEventListener("mousemove", activate);
    button.addEventListener("focus", activate);
    button.addEventListener("click", () => navigateToResult(result));
    return button;
  }

  function renderResults(results) {
    const container = resultsContainer();
    if (!container) return;

    clearResults();
    currentResults = Array.isArray(results) ? results : [];

    if (!currentResults.length) {
      setState("No matching docs found.");
      return;
    }

    hideState();
    const fragment = document.createDocumentFragment();
    currentResults.forEach((result, index) => {
      fragment.appendChild(buildResultElement(result, index));
    });
    container.appendChild(fragment);
    selectedIndex = 0;
    syncActiveResult();
  }

  async function performSearch(rawQuery) {
    const query = rawQuery.trim();
    if (!query) {
      abortSearch();
      clearResults();
      setState("Start typing to search pages, headings, and content.");
      return;
    }

    const requestId = ++searchRequestId;
    abortSearch();
    searchController = new AbortController();
    setState("Searching…");

    try {
      const response = await fetch(
        `${SEARCH_ENDPOINT}?q=${encodeURIComponent(query)}&limit=${RESULT_LIMIT}`,
        {
          signal: searchController.signal,
          headers: { Accept: "application/json" },
        }
      );

      if (!response.ok) {
        throw new Error(`Search request failed with ${response.status}`);
      }

      const payload = await response.json();
      if (requestId !== searchRequestId) {
        return;
      }

      renderResults(payload.results || []);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      clearResults();
      setState("Search is unavailable right now.");
    }
  }

  function scheduleSearch(rawQuery) {
    if (searchTimer) {
      clearTimeout(searchTimer);
    }
    searchTimer = setTimeout(() => {
      searchTimer = null;
      void performSearch(rawQuery);
    }, SEARCH_DEBOUNCE_MS);
  }

  function openSearch() {
    const element = overlay();
    const searchInput = input();
    if (!(element instanceof HTMLElement) || !(searchInput instanceof HTMLInputElement)) {
      return;
    }

    lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setHidden(element, false);
    setDocumentOpenState(true);
    searchInput.focus();
    searchInput.select();
    scheduleSearch(searchInput.value);
  }

  function closeSearch() {
    const element = overlay();
    if (!(element instanceof HTMLElement)) {
      return;
    }

    setHidden(element, true);
    setDocumentOpenState(false);
    abortSearch();
    if (searchTimer) {
      clearTimeout(searchTimer);
      searchTimer = null;
    }
    if (lastFocusedElement && document.contains(lastFocusedElement)) {
      lastFocusedElement.focus();
    }
    lastFocusedElement = null;
  }

  document.addEventListener("click", (event) => {
    const openButton = event.target.closest(OPEN_SELECTOR);
    if (openButton) {
      event.preventDefault();
      openSearch();
      return;
    }

    if (event.target.closest(CLOSE_SELECTOR)) {
      event.preventDefault();
      closeSearch();
    }
  });

  document.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement) || !target.matches(INPUT_SELECTOR)) {
      return;
    }
    scheduleSearch(target.value);
  });

  document.addEventListener("keydown", (event) => {
    const key = event.key.toLowerCase();
    const shortcutPressed = (event.metaKey || event.ctrlKey) && !event.altKey && key === "k";

    if (shortcutPressed) {
      event.preventDefault();
      openSearch();
      return;
    }

    if (!isOpen()) {
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      closeSearch();
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveSelection(1);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      moveSelection(-1);
      return;
    }

    if (event.key === "Enter" && selectedIndex >= 0) {
      event.preventDefault();
      navigateToResult(currentResults[selectedIndex]);
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncShortcutLabels, { once: true });
  } else {
    syncShortcutLabels();
  }

  document.addEventListener("htmx:afterSwap", syncShortcutLabels);
})();

(() => {
  const STORAGE_KEY = "markserv-theme";
  const SYSTEM_THEME = "system";
  const LIGHT_THEME = "light";
  const DARK_THEME = "dark";
  const THEME_BTN_SELECTOR = "[data-theme-btn]";
  const DARK_MODE_QUERY = "(prefers-color-scheme: dark)";
  const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
  const THEME_OPTIONS = [SYSTEM_THEME, LIGHT_THEME, DARK_THEME];
  const THEME_VIEW_TRANSITION_CLASS = "theme-view-transition";
  const THEME_VIEW_TRANSITION_CLASSES = ["theme-view-to-light", "theme-view-to-dark"];
  let themeViewTransitionId = 0;

  function isThemePreference(value) {
    return THEME_OPTIONS.includes(value);
  }

  function storedThemePreference() {
    try {
      const theme = window.localStorage.getItem(STORAGE_KEY);
      return isThemePreference(theme) ? theme : null;
    } catch {
      return null;
    }
  }

  function themePreference() {
    return storedThemePreference() ?? SYSTEM_THEME;
  }

  function systemTheme() {
    return window.matchMedia(DARK_MODE_QUERY).matches ? DARK_THEME : LIGHT_THEME;
  }

  function prefersReducedMotion() {
    return window.matchMedia(REDUCED_MOTION_QUERY).matches;
  }

  function resolvedTheme(preference) {
    return preference === SYSTEM_THEME ? systemTheme() : preference;
  }

  function currentTheme() {
    return document.documentElement.dataset.theme || resolvedTheme(themePreference());
  }

  const THEME_STYLESHEET_PAIRS = [
    ["github-markdown-light", "github-markdown-dark"],
    ["pygments-light", "pygments-dark"],
  ];

  function setStylesheetMedia(theme) {
    THEME_STYLESHEET_PAIRS.forEach(([lightId, darkId]) => {
      const lightStylesheet = document.getElementById(lightId);
      const darkStylesheet = document.getElementById(darkId);

      if (!(lightStylesheet instanceof HTMLLinkElement) || !(darkStylesheet instanceof HTMLLinkElement)) {
        return;
      }

      lightStylesheet.media = theme === LIGHT_THEME ? "all" : "not all";
      darkStylesheet.media = theme === DARK_THEME ? "all" : "not all";
    });
  }

  const THEME_LABELS = { system: "System", light: "Light", dark: "Dark" };

  function updateThemeControls(preference) {
    document.querySelectorAll(THEME_BTN_SELECTOR).forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.themeBtn === preference);
    });
    document.querySelectorAll(".theme-label").forEach((el) => {
      el.textContent = THEME_LABELS[preference] || "";
    });
  }

  function applyTheme(preference = themePreference()) {
    const theme = resolvedTheme(preference);
    document.documentElement.dataset.theme = theme;
    setStylesheetMedia(theme);
    updateThemeControls(preference);
  }

  function saveThemePreference(preference) {
    try {
      window.localStorage.setItem(STORAGE_KEY, preference);
    } catch {
      // Ignore storage failures.
    }
  }

  applyTheme();

  document.addEventListener("DOMContentLoaded", () => {
    updateThemeControls(themePreference());
  });

  document.addEventListener("htmx:afterSwap", () => {
    updateThemeControls(themePreference());
  });

  let transitionTimer = null;
  const TRANSITION_CLASSES = ["theme-to-light", "theme-to-dark"];

  function enableTransition(toTheme) {
    if (transitionTimer) clearTimeout(transitionTimer);
    const cls = toTheme === DARK_THEME ? "theme-to-dark" : "theme-to-light";
    document.documentElement.classList.remove(...TRANSITION_CLASSES);
    document.documentElement.classList.add(cls);
    const duration = 1300;
    transitionTimer = setTimeout(() => {
      document.documentElement.classList.remove(cls);
      transitionTimer = null;
    }, duration);
  }

  function themeViewTransitionClass(toTheme) {
    return toTheme === DARK_THEME ? "theme-view-to-dark" : "theme-view-to-light";
  }

  function finishThemeTransition(transitionId) {
    if (transitionId !== themeViewTransitionId) {
      return;
    }
    document.documentElement.classList.remove(THEME_VIEW_TRANSITION_CLASS, ...THEME_VIEW_TRANSITION_CLASSES);
  }

  function applyThemeSelection(preference) {
    const nextTheme = resolvedTheme(preference);
    const visualThemeChanged = currentTheme() !== nextTheme;

    saveThemePreference(preference);

    if (!visualThemeChanged) {
      applyTheme(preference);
      return;
    }

    if (prefersReducedMotion()) {
      applyTheme(preference);
      return;
    }

    if (!document.startViewTransition) {
      enableTransition(nextTheme);
      applyTheme(preference);
      return;
    }

    const transitionId = ++themeViewTransitionId;
    document.documentElement.classList.remove(...THEME_VIEW_TRANSITION_CLASSES);
    document.documentElement.classList.add(THEME_VIEW_TRANSITION_CLASS, themeViewTransitionClass(nextTheme));

    let transition;
    try {
      transition = document.startViewTransition(() => {
        applyTheme(preference);
      });
    } catch {
      finishThemeTransition(transitionId);
      enableTransition(nextTheme);
      applyTheme(preference);
      return;
    }

    transition.finished.finally(() => {
      finishThemeTransition(transitionId);
    });
  }

  document.addEventListener("click", (event) => {
    const btn = event.target.closest(THEME_BTN_SELECTOR);
    if (!btn || !isThemePreference(btn.dataset.themeBtn)) {
      return;
    }

    applyThemeSelection(btn.dataset.themeBtn);
  });

  const mediaQuery = window.matchMedia(DARK_MODE_QUERY);
  const handleSystemThemeChange = () => {
    if (themePreference() !== SYSTEM_THEME) {
      return;
    }
    applyTheme(SYSTEM_THEME);
  };

  if (typeof mediaQuery.addEventListener === "function") {
    mediaQuery.addEventListener("change", handleSystemThemeChange);
  } else {
    mediaQuery.addListener(handleSystemThemeChange);
  }

  window.addEventListener("storage", (event) => {
    if (event.key !== STORAGE_KEY) {
      return;
    }
    applyTheme();
  });
})();

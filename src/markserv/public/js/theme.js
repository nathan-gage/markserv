(() => {
  const STORAGE_KEY = "markserv-theme";
  const SYSTEM_THEME = "system";
  const LIGHT_THEME = "light";
  const DARK_THEME = "dark";
  const THEME_SELECT_SELECTOR = "[data-theme-select]";
  const DARK_MODE_QUERY = "(prefers-color-scheme: dark)";
  const THEME_OPTIONS = [SYSTEM_THEME, LIGHT_THEME, DARK_THEME];

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

  function resolvedTheme(preference) {
    return preference === SYSTEM_THEME ? systemTheme() : preference;
  }

  function setStylesheetMedia(theme) {
    const lightStylesheet = document.getElementById("github-markdown-light");
    const darkStylesheet = document.getElementById("github-markdown-dark");

    if (!(lightStylesheet instanceof HTMLLinkElement) || !(darkStylesheet instanceof HTMLLinkElement)) {
      return;
    }

    lightStylesheet.media = theme === LIGHT_THEME ? "all" : "not all";
    darkStylesheet.media = theme === DARK_THEME ? "all" : "not all";
  }

  function updateThemeControls(preference) {
    document.querySelectorAll(THEME_SELECT_SELECTOR).forEach((select) => {
      if (select instanceof HTMLSelectElement) {
        select.value = preference;
      }
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

  document.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }

    const select = target.closest(THEME_SELECT_SELECTOR);
    if (!(select instanceof HTMLSelectElement) || !isThemePreference(select.value)) {
      return;
    }

    saveThemePreference(select.value);
    applyTheme(select.value);
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

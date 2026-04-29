(() => {
  const MERMAID_MODULE_URL = "/public/vendor/mermaid.esm.min.mjs";
  const MERMAID_SELECTOR = ".markdown-body .mermaid";
  const DARK_THEME = "dark";

  let mermaidPromise = null;

  function loadMermaid() {
    mermaidPromise ??= import(MERMAID_MODULE_URL).then((module) => module.default ?? module);
    return mermaidPromise;
  }

  function currentMermaidTheme() {
    return document.documentElement.dataset.theme === DARK_THEME ? "dark" : "default";
  }

  function prepareNode(node, force) {
    if (!(node instanceof HTMLElement)) {
      return false;
    }

    node.dataset.mermaidSource ??= node.textContent || "";

    if (force && node.hasAttribute("data-processed")) {
      node.removeAttribute("data-processed");
      node.textContent = node.dataset.mermaidSource;
    }

    return !node.hasAttribute("data-processed");
  }

  async function renderMermaid({ force = false } = {}) {
    const nodes = Array.from(document.querySelectorAll(MERMAID_SELECTOR)).filter((node) => prepareNode(node, force));
    if (nodes.length === 0) {
      return;
    }

    try {
      const mermaid = await loadMermaid();
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: currentMermaidTheme(),
      });
      await mermaid.run({ nodes, suppressErrors: true });
      nodes.forEach((node) => node.classList.remove("mermaid-error"));
    } catch (error) {
      console.error("Unable to render Mermaid diagrams", error);
      nodes.forEach((node) => node.classList.add("mermaid-error"));
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    renderMermaid();
  });

  document.addEventListener("htmx:afterSwap", () => {
    renderMermaid();
  });

  new MutationObserver((mutations) => {
    if (mutations.some((mutation) => mutation.attributeName === "data-theme")) {
      renderMermaid({ force: true });
    }
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
})();

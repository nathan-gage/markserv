(() => {
  let timer = null;
  let activeBtn = null;

  document.addEventListener("click", (e) => {
    const group = e.target.closest(".content-path-group");
    if (!group) return;

    const btn = group.querySelector(".copy-btn");
    if (!btn) return;

    const text = btn.dataset.copyText;
    if (!text) return;

    // If a different button was active, reset it.
    if (activeBtn && activeBtn !== btn) {
      activeBtn.classList.remove("is-copied");
    }

    navigator.clipboard.writeText(text).then(() => {
      if (timer) clearTimeout(timer);
      btn.classList.add("is-copied");
      activeBtn = btn;
      timer = setTimeout(() => {
        btn.classList.remove("is-copied");
        activeBtn = null;
        timer = null;
      }, 1500);
    });
  });
})();

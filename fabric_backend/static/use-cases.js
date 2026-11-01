// /use-cases (n59): each example's map, drawn by map.js (the renderer /check uses) from the engine events embedded in
// the page. The findings under a map are buttons that mark their relationship or table, as on /check; with
// prefers-reduced-motion the map appears without animation.
(function () {
  "use strict";
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.querySelectorAll("figure[data-map]").forEach((fig) => {
    let data;
    try { data = JSON.parse(fig.querySelector(".uc-map-data").textContent); } catch (e) { return; }
    const map = new window.KrusMap.MapView(fig.querySelector(".check-map"), { still });
    data.steps.forEach((s) => map.update(s));
    const card = fig.closest(".uc-ex");
    const buttons = card.querySelectorAll("[data-finding]");
    buttons.forEach((b) => b.addEventListener("click", () => {
      const f = data.findings[Number(b.dataset.finding)];
      const on = b.getAttribute("aria-pressed") !== "true" && window.KrusMap.where(f).some((x) => map.highlight(x));
      if (!on) map.highlight(null);
      buttons.forEach((o) => o.setAttribute("aria-pressed", String(o === b && on)));
    }));
  });
})();

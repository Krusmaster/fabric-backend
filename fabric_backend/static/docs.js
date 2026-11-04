/* n86a: /docs was one long page; its headings now live on sub-pages. An old link such as /docs#test-status is sent on to
   the page that has that heading, using the map /docs carries (built from the headings in DOCS.md, never by hand).
   Without JavaScript /docs shows the overview with links to every page. */
(function () {
  function go() {
    var el = document.getElementById('docs-anchors');
    if (!el || !location.hash) return;
    var map, id;
    try { map = JSON.parse(el.textContent); id = decodeURIComponent(location.hash.slice(1)); } catch (e) { return; }
    if (!Object.prototype.hasOwnProperty.call(map, id)) return;
    var to = map[id];
    if (typeof to !== 'string' || !/^\/docs\/[a-z0-9\/-]+$/.test(to)) return;
    location.replace(to + '#' + encodeURIComponent(id));
  }
  go();
  window.addEventListener('hashchange', go);
})();

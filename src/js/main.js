// Small enhancements. Every feature here is optional: without JavaScript the page
// still shows all content, the static map picture and plain links.
(function () {
  "use strict";
  var doc = document.documentElement;
  var hasIO = "IntersectionObserver" in window;
  doc.classList.add("reveal-ready");

  // Interface text for this page's language, written into the page by the build
  var T = {};
  try { T = JSON.parse(document.getElementById("site-i18n").textContent); } catch (e) {}
  var lang = T.lang || doc.lang || "en";
  var NUM = T.num || { group: ",", decimal: "." };
  // Numbers written the way this page's language writes them (the build uses the same rules)
  function fmt(v, decimals) {
    var parts = Number(v).toFixed(decimals || 0).split(".");
    return parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, NUM.group) + (parts[1] ? NUM.decimal + parts[1] : "");
  }
  function fill(s, vals) {
    return String(s).replace(/\{(\w+)\}/g, function (m, k) { return k in vals ? vals[k] : m; });
  }
  function store(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }
  function read(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // Theme toggle: follows the OS until the visitor picks; the choice stays in this browser
  var toggle = document.querySelector("[data-theme-toggle]");
  if (toggle) {
    var media = window.matchMedia("(prefers-color-scheme: dark)");
    var current = function () { return doc.dataset.theme || (media.matches ? "dark" : "light"); };
    var label = function () {
      toggle.querySelector(".visually-hidden").textContent = current() === "dark" ? T.theme_to_light : T.theme_to_dark;
    };
    toggle.hidden = false;
    label();
    toggle.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      doc.dataset.theme = next;
      store("theme", next);
      document.querySelectorAll('meta[name="theme-color"]').forEach(function (m) {
        m.setAttribute("content", next === "dark" ? "#0f1613" : "#f7f6f1");
      });
      label();
    });
    if (media.addEventListener) media.addEventListener("change", label);
  }

  // Long contents lists start open only where there is room beside the text
  if (window.matchMedia("(min-width: 1100px)").matches) {
    document.querySelectorAll("details[data-open-wide]").forEach(function (d) { d.open = true; });
  }

  // Before a jump to a section on this page, lay out every section at its real height so the jump lands right
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("a[href*='#']");
    if (!a) return;
    var u = new URL(a.href, location.href);
    if (u.pathname === location.pathname && u.hash) doc.classList.add("cv-off");
  });
  window.addEventListener("hashchange", function () { doc.classList.add("cv-off"); });

  // Mark the menu item for the section of the site you are in (Services and its pages)
  document.querySelectorAll(".site-nav a").forEach(function (a) {
    var u = new URL(a.href, location.href);
    if (!u.hash && !/^\/([a-z]{2}\/)?$/.test(u.pathname) && location.pathname.indexOf(u.pathname) === 0) a.setAttribute("aria-current", "page");
  });

  // Menu that scrolls sideways on phones: fade the far edge while more items are hidden there
  var siteNav = document.querySelector(".site-nav");
  if (siteNav) {
    var navMore = function () {
      siteNav.classList.toggle("has-more", siteNav.scrollWidth - siteNav.clientWidth - Math.abs(siteNav.scrollLeft) > 4);
    };
    siteNav.addEventListener("scroll", navMore, { passive: true });
    window.addEventListener("resize", navMore);
    navMore();
  }

  // Language menu: closes on Escape or a click elsewhere
  var langMenu = document.querySelector("[data-lang-menu]");
  if (langMenu) {
    document.addEventListener("click", function (ev) { if (langMenu.open && !langMenu.contains(ev.target)) langMenu.open = false; });
    langMenu.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && langMenu.open) { langMenu.open = false; langMenu.querySelector("summary").focus(); }
    });
  }

  // Language: a choice made in the menu is remembered, and the head script honours it on later visits
  document.querySelectorAll("[data-lang-choice]").forEach(function (a) {
    a.addEventListener("click", function () {
      store("lang", a.dataset.langChoice);
      if (location.hash && a.href.indexOf("#") < 0) a.href += location.hash;
    });
  });

  // With no choice made yet, offer the version that matches the browser's language (never the location)
  (function suggest() {
    if (read("lang") || read("lang-suggest") === "off" || !T.suggest) return;
    var wanted = null;
    (navigator.languages || [navigator.language || ""]).some(function (l) {
      var code = String(l).slice(0, 2).toLowerCase();
      if (code === lang) return true;
      if (T.suggest[code] && document.querySelector('link[rel="alternate"][hreflang="' + code + '"]')) { wanted = code; return true; }
      return false;
    });
    if (!wanted) return;
    var s = T.suggest[wanted];
    var href = document.querySelector('link[rel="alternate"][hreflang="' + wanted + '"]').getAttribute("href");
    var box = document.createElement("aside");
    box.className = "lang-suggest";
    box.lang = wanted;
    box.dir = s.dir || "ltr";
    box.setAttribute("aria-label", s.text);
    var p = document.createElement("p");
    p.textContent = s.text;
    var actions = document.createElement("div");
    var go = document.createElement("a");
    go.className = "btn btn-sm";
    go.href = new URL(href).pathname + location.hash;
    go.hreflang = wanted;
    go.textContent = s["switch"];
    go.addEventListener("click", function () { store("lang", wanted); });
    var stay = document.createElement("button");
    stay.type = "button";
    stay.className = "btn btn-sm btn-ghost";
    stay.textContent = s.stay;
    stay.addEventListener("click", function () { store("lang-suggest", "off"); box.remove(); });
    actions.appendChild(go);
    actions.appendChild(stay);
    box.appendChild(p);
    box.appendChild(actions);
    document.body.appendChild(box);
  })();

  // Highlight the nav link for the section in view (home page only)
  var navLinks = document.querySelectorAll('.site-nav a[href^="#"]');
  if (navLinks.length && hasIO) {
    var byId = {};
    navLinks.forEach(function (a) {
      var target = document.getElementById(a.getAttribute("href").slice(1));
      if (target) byId[target.id] = a;
    });
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting || !byId[e.target.id]) return;
        navLinks.forEach(function (a) { a.removeAttribute("aria-current"); });
        byId[e.target.id].setAttribute("aria-current", "true");
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    Object.keys(byId).forEach(function (id) { spy.observe(document.getElementById(id)); });
  }

  // Floating "Book a call" on phones once the hero has scrolled away
  var cta = document.querySelector("[data-mobile-cta]");
  var hero = document.querySelector(".hero, .case-hero");
  if (cta && hero && hasIO) {
    var state = { heroOut: false, endIn: false };
    var update = function () {
      var show = state.heroOut && !state.endIn;
      cta.classList.toggle("is-visible", show);
      cta.setAttribute("aria-hidden", show ? "false" : "true");
      cta.tabIndex = show ? 0 : -1;
    };
    update();
    new IntersectionObserver(function (e) { state.heroOut = !e[0].isIntersecting; update(); }).observe(hero);
    var ends = document.querySelectorAll("#contact, .aside-cta, .site-footer");
    var visible = new Set();
    var eo = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) visible.add(e.target); else visible.delete(e.target); });
      state.endIn = visible.size > 0;
      update();
    });
    ends.forEach(function (el) { eo.observe(el); });
  }

  // Copy the email address
  var live = document.createElement("span");
  live.className = "visually-hidden";
  live.setAttribute("aria-live", "polite");
  document.body.appendChild(live);
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    if (!navigator.clipboard) return;
    btn.hidden = false;
    btn.setAttribute("aria-label", T.copy_label);
    var text = btn.querySelector("span");
    btn.addEventListener("click", function () {
      navigator.clipboard.writeText(btn.dataset.copy).then(function () {
        text.textContent = T.copied;
        btn.classList.add("is-done");
        live.textContent = T.email_copied;
        setTimeout(function () { text.textContent = T.copy; btn.classList.remove("is-done"); live.textContent = ""; }, 2000);
      });
    });
  });

  // Sector filter on the service lists
  var filter = document.querySelector("[data-sector-filter]");
  var sectorList = document.querySelector("[data-sector-list]");
  if (filter && sectorList) {
    var sectorStatus = document.querySelector("[data-sector-status]");
    filter.hidden = false;
    filter.addEventListener("click", function (ev) {
      var b = ev.target.closest("button[data-sector]");
      if (!b) return;
      filter.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      var key = b.dataset.sector;
      var shown = 0;
      sectorList.querySelectorAll("li[data-sectors]").forEach(function (li) {
        var show = key === "all" || li.dataset.sectors.split(" ").indexOf(key) > -1;
        li.hidden = !show;
        if (show) shown++;
      });
      if (sectorStatus) sectorStatus.textContent = fill(key === "all" ? T.services_count : T.services_for, { n: shown, sector: b.textContent });
    });
  }

  // Request builder: turns the ticked options into an email in the visitor's own mail app
  var brief = document.querySelector("[data-brief]");
  if (brief) {
    brief.hidden = false;
    var briefStatus = brief.querySelector(".brief-status");
    var compose = function () {
      var fd = new FormData(brief);
      var place = (fd.get("place") || "").trim();
      var where = fd.get("where") || "";
      var sep = lang === "fr" ? " : " : ": ";
      var line = function (label, values) { return values.length ? label + sep + values.join(", ") : ""; };
      var lines = [
        T.brief_hello, "", T.brief_book, "",
        line(T.brief_services, fd.getAll("service")),
        where || place ? T.brief_site + sep + [where, place].filter(Boolean).join(", ") : "",
        line(T.brief_timing, fd.getAll("when")),
        line(T.brief_data, fd.getAll("data")),
        (fd.get("decide") || "").trim() ? T.brief_decide + sep + fd.get("decide").trim() : "",
        "", T.brief_org, T.brief_times
      ];
      return lines.filter(function (l, i) { return l !== "" || lines[i - 1] !== ""; }).join("\r\n");
    };
    brief.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var services = new FormData(brief).getAll("service");
      var subject = T.brief_subject + (services.length ? (lang === "fr" ? " : " : ": ") + services.slice(0, 2).join(", ") : "");
      window.location.href = "mailto:" + brief.dataset.email +
        "?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(compose());
      briefStatus.textContent = T.brief_opening;
    });
    var copyBrief = brief.querySelector("[data-brief-copy]");
    if (navigator.clipboard) {
      copyBrief.addEventListener("click", function () {
        navigator.clipboard.writeText(compose()).then(function () { briefStatus.textContent = T.brief_copied; });
      });
    } else {
      copyBrief.hidden = true;
    }
  }

  // Count the headline numbers up once, when they come into view; the real numbers are already in the page
  var counters = document.querySelectorAll("[data-count]");
  if (counters.length && hasIO && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    var co = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        co.unobserve(e.target);
        var el = e.target;
        var text = el.textContent.trim();
        var plain = text.replace(/[\s\u00a0\u202f]/g, "").split(NUM.group).join("").replace(NUM.decimal, ".");
        var target = parseFloat(plain);
        if (isNaN(target)) return;
        var decimals = (plain.split(".")[1] || "").length;
        var start = performance.now();
        var tick = function (now) {
          var t = Math.min(1, (now - start) / 1100);
          var v = target * (1 - Math.pow(1 - t, 3));
          el.textContent = fmt(v, decimals);
          if (t < 1) requestAnimationFrame(tick); else el.textContent = text;
        };
        requestAnimationFrame(tick);
      });
    }, { threshold: 0.6 });
    counters.forEach(function (c) { co.observe(c); });
  }

  // Reading progress on case studies, service pages and the methods log
  var article = document.querySelector(".case-page, .service-page, .doc-page");
  if (article) {
    var bar = document.createElement("div");
    bar.className = "read-progress";
    bar.setAttribute("aria-hidden", "true");
    bar.innerHTML = "<span></span>";
    document.body.appendChild(bar);
    var fill = bar.firstChild;
    var ticking = false;
    var measure = function () {
      var r = article.getBoundingClientRect();
      var total = r.height - window.innerHeight;
      var p = total > 0 ? Math.min(1, Math.max(0, -r.top / total)) : 1;
      fill.style.transform = "scaleX(" + p + ")";
      ticking = false;
    };
    window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(measure); } }, { passive: true });
    measure();
  }

  // Enlarge images in a dialog; without JavaScript the link opens the image itself
  var dialog;
  document.querySelectorAll("[data-lightbox]").forEach(function (link) {
    link.addEventListener("click", function (ev) {
      if (!window.HTMLDialogElement) return;
      ev.preventDefault();
      if (!dialog) {
        dialog = document.createElement("dialog");
        dialog.className = "lightbox";
        dialog.setAttribute("aria-label", T.lightbox_label);
        dialog.innerHTML = '<div class="lightbox-bar"><button type="button"></button></div><img alt="">';
        dialog.querySelector("button").textContent = T.close;
        document.body.appendChild(dialog);
        dialog.querySelector("button").addEventListener("click", function () { dialog.close(); });
        dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
      }
      var thumb = link.querySelector("img");
      var img = dialog.querySelector("img");
      img.src = link.href;
      img.alt = thumb ? thumb.alt : "";
      dialog.showModal();
    });
  });

  // Lagos Access Map: Leaflet and the data load only when the map scrolls near
  var panel = document.querySelector("[data-access-map]");
  if (panel && hasIO) {
    var io = new IntersectionObserver(function (entries) {
      if (!entries[0].isIntersecting) return;
      io.disconnect();
      startMap(panel);
    }, { rootMargin: "300px 0px" });
    io.observe(panel);
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src; s.onload = resolve; s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  function startMap(panel) {
    var status = panel.querySelector("[data-map-status]");
    status.textContent = T.map_loading;
    var css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "/vendor/leaflet/leaflet.css";
    document.head.appendChild(css);
    Promise.all([
      loadScript("/vendor/leaflet/leaflet.js"),
      fetch(panel.dataset.src).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    ]).then(function (res) {
      buildMap(panel, res[1]);
      status.textContent = "";
    }).catch(function () {
      status.textContent = T.map_failed;
    });
  }

  var COLOURS = ["#3987e5", "#d95926", "#199e70", "#8a918d"]; // same order as the .dot-N classes in style.css
  var LABELS = T.map_legend || ["Hospital", "Clinic or doctor", "Pharmacy", "Other"];
  var SLOT = [0, 1, 1, 2, 3]; // hospital, clinic, doctors, pharmacy, other
  var PANEL = "#0d1714";

  function buildMap(panel, data) {
    var map = L.map(panel.querySelector(".map-live"), {
      zoomSnap: 0.25, scrollWheelZoom: false, preferCanvas: true, minZoom: 8, maxZoom: 16
    });
    map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
    map.attributionControl.addAttribution(fill(esc(T.map_attribution), {
      osm: '<a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>', date: esc(T.pulled || data.pulled)
    }));

    var lgas = L.geoJSON(data.lgas, {
      style: { color: "#e7ede9", weight: 1, opacity: 0.4, fillColor: "#ffffff", fillOpacity: 0.03 },
      onEachFeature: function (f, layer) {
        var c = f.properties.counts;
        var total = c ? c.reduce(function (a, b) { return a + b; }, 0) : null;
        layer.bindTooltip("<strong>" + esc(f.properties.name) + "</strong>" +
          (total === null ? "" : "<span>" + esc(total === 1 ? T.map_in_osm_one : fill(T.map_in_osm, { n: fmt(total) })) + "</span>"),
          { sticky: true, direction: "top" });
        layer.on({
          mouseover: function () { layer.setStyle({ fillOpacity: 0.1, opacity: 0.85 }); },
          mouseout: function () { lgas.resetStyle(layer); }
        });
      }
    }).addTo(map);
    var bounds = lgas.getBounds();
    var fit = function () { map.fitBounds(bounds, { padding: [10, 10] }); };
    fit();
    map.setMaxBounds(bounds.pad(0.5));

    var groups = [L.layerGroup(), L.layerGroup(), L.layerGroup(), L.layerGroup()];
    var counts = [0, 0, 0, 0];
    data.facilities.forEach(function (p) {
      var s = SLOT[p[2]];
      counts[s]++;
      L.circleMarker([p[1], p[0]], { radius: 5, color: PANEL, weight: 1.5, fillColor: COLOURS[s], fillOpacity: 1 })
        .bindTooltip("<strong>" + esc(p[3] || T.map_unnamed) + "</strong><span>" + esc(LABELS[s]) + "</span>",
          { direction: "top", offset: [0, -4] })
        .addTo(groups[s]);
    });
    [0, 1, 2, 3].sort(function (a, b) { return counts[b] - counts[a]; })
      .forEach(function (s) { groups[s].addTo(map); }); // big groups first, small ones on top

    var legend = panel.parentNode.querySelector("[data-map-legend]");
    legend.innerHTML = "";
    legend.setAttribute("role", "group");
    legend.setAttribute("aria-label", T.map_filter);
    LABELS.forEach(function (label, s) {
      var b = document.createElement("button");
      b.type = "button";
      b.setAttribute("aria-pressed", "true");
      b.innerHTML = '<i class="dot-' + s + '"></i>' + esc(label) + " <b>" + fmt(counts[s]) + "</b>";
      b.addEventListener("click", function () {
        var on = b.getAttribute("aria-pressed") === "true";
        b.setAttribute("aria-pressed", on ? "false" : "true");
        if (on) map.removeLayer(groups[s]); else groups[s].addTo(map);
      });
      legend.appendChild(b);
    });
    var reset = document.createElement("button");
    reset.type = "button";
    reset.className = "map-reset";
    reset.textContent = T.map_reset;
    reset.addEventListener("click", fit);
    legend.appendChild(reset);

    // The wheel zooms the map only after the visitor engages with it, so the page still scrolls
    map.on("focus click", function () { map.scrollWheelZoom.enable(); });
    map.on("blur mouseout", function () { map.scrollWheelZoom.disable(); });
    panel.classList.add("is-live");
    // The section may have been skipped by content-visibility when the map was built; re-measure once seen
    var seen = new IntersectionObserver(function (entries) {
      if (!entries[0].isIntersecting) return;
      seen.disconnect();
      map.invalidateSize();
      fit();
    });
    seen.observe(panel);
  }
})();

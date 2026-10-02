// Small enhancements. Every feature here is optional: without JavaScript the page
// still shows all content, the static map picture and plain links.
(function () {
  "use strict";
  var doc = document.documentElement;
  var hasIO = "IntersectionObserver" in window;
  doc.classList.add("reveal-ready");

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
      toggle.querySelector(".visually-hidden").textContent =
        "Switch to " + (current() === "dark" ? "light" : "dark") + " theme";
    };
    toggle.hidden = false;
    label();
    toggle.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      doc.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) {}
      document.querySelectorAll('meta[name="theme-color"]').forEach(function (m) {
        m.setAttribute("content", next === "dark" ? "#0f1613" : "#f7f6f1");
      });
      label();
    });
    if (media.addEventListener) media.addEventListener("change", label);
  }

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

  // Fade sections in as they arrive; siblings arrive one after another
  var reveals = document.querySelectorAll("[data-reveal]");
  if (hasIO) {
    reveals.forEach(function (el) {
      var siblings = el.parentNode.querySelectorAll(":scope > [data-reveal]");
      var i = Array.prototype.indexOf.call(siblings, el);
      if (i > 0) el.style.transitionDelay = Math.min(i, 4) * 70 + "ms";
    });
    var ro = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("is-in"); ro.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    reveals.forEach(function (el) { ro.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add("is-in"); });
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
    btn.setAttribute("aria-label", "Copy email address");
    var text = btn.querySelector("span");
    btn.addEventListener("click", function () {
      navigator.clipboard.writeText(btn.dataset.copy).then(function () {
        text.textContent = "Copied";
        btn.classList.add("is-done");
        live.textContent = "Email address copied";
        setTimeout(function () { text.textContent = "Copy"; btn.classList.remove("is-done"); live.textContent = ""; }, 2000);
      });
    });
  });

  // Enlarge images in a dialog; without JavaScript the link opens the image itself
  var dialog;
  document.querySelectorAll("[data-lightbox]").forEach(function (link) {
    link.addEventListener("click", function (ev) {
      if (!window.HTMLDialogElement) return;
      ev.preventDefault();
      if (!dialog) {
        dialog = document.createElement("dialog");
        dialog.className = "lightbox";
        dialog.setAttribute("aria-label", "Enlarged image");
        dialog.innerHTML = '<div class="lightbox-bar"><button type="button">Close</button></div><img alt="">';
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
    status.textContent = "Loading the interactive map…";
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
      status.textContent = "The interactive map could not load. The picture shows the same data.";
    });
  }

  var COLOURS = ["#3987e5", "#d95926", "#199e70", "#8a918d"];
  var LABELS = ["Hospital", "Clinic or doctor", "Pharmacy", "Other"];
  var SLOT = [0, 1, 1, 2, 3]; // hospital, clinic, doctors, pharmacy, other
  var PANEL = "#0d1714";

  function buildMap(panel, data) {
    var map = L.map(panel.querySelector(".map-live"), {
      zoomSnap: 0.25, scrollWheelZoom: false, preferCanvas: true, minZoom: 8, maxZoom: 16
    });
    map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
    map.attributionControl.addAttribution(
      'Data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>, pulled ' + esc(data.pulled));

    var lgas = L.geoJSON(data.lgas, {
      style: { color: "#e7ede9", weight: 1, opacity: 0.4, fillColor: "#ffffff", fillOpacity: 0.03 },
      onEachFeature: function (f, layer) {
        var c = f.properties.counts;
        var total = c ? c.reduce(function (a, b) { return a + b; }, 0) : null;
        layer.bindTooltip("<strong>" + esc(f.properties.name) + "</strong>" +
          (total === null ? "" : "<span>" + total + " facilit" + (total === 1 ? "y" : "ies") + " in OpenStreetMap</span>"),
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
        .bindTooltip("<strong>" + esc(p[3] || "Unnamed facility") + "</strong><span>" + LABELS[s] + "</span>",
          { direction: "top", offset: [0, -4] })
        .addTo(groups[s]);
    });
    [0, 1, 2, 3].sort(function (a, b) { return counts[b] - counts[a]; })
      .forEach(function (s) { groups[s].addTo(map); }); // big groups first, small ones on top

    var legend = panel.parentNode.querySelector("[data-map-legend]");
    legend.innerHTML = "";
    legend.setAttribute("role", "group");
    legend.setAttribute("aria-label", "Show or hide facility types");
    LABELS.forEach(function (label, s) {
      var b = document.createElement("button");
      b.type = "button";
      b.setAttribute("aria-pressed", "true");
      b.style.setProperty("--c", COLOURS[s]);
      b.innerHTML = "<i></i>" + label + " <b>" + counts[s] + "</b>";
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
    reset.textContent = "Reset view";
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

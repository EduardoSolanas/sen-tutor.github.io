/* ============================================================
   SEN Tutor — Eva · 2026
   Plain JavaScript: navigation, calm mode, reveals, dialogs and contact form
   ============================================================ */
(function () {
  "use strict";

  var docEl = document.documentElement;

  /* ---------- footer year ---------- */
  var yearEls = document.querySelectorAll("[data-year]");
  var now = new Date().getFullYear();
  yearEls.forEach(function (el) { el.textContent = now; });

  /* ---------- sticky header shadow ---------- */
  var header = document.querySelector(".site-header");
  function onScroll() {
    if (header) header.classList.toggle("scrolled", window.scrollY > 12);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ---------- mobile nav ---------- */
  var navToggle = document.querySelector(".nav-toggle");
  var mainNav = document.querySelector(".main-nav");
  if (navToggle && mainNav) {
    function closeNav() {
      mainNav.classList.remove("open");
      navToggle.setAttribute("aria-expanded", "false");
      navToggle.textContent = "☰";
    }
    navToggle.addEventListener("click", function () {
      var open = mainNav.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
      navToggle.textContent = open ? "✕" : "☰";
    });
    mainNav.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", closeNav);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && mainNav.classList.contains("open")) {
        closeNav();
        navToggle.focus();
      }
    });
    document.addEventListener("click", function (event) {
      if (!mainNav.classList.contains("open")) return;
      if (!mainNav.contains(event.target) && !navToggle.contains(event.target)) closeNav();
    });
  }

  /* ---------- calm mode (sensory friendly) ---------- */
  var CALM_KEY = "eva-calm-mode";
  var calmToggle = document.querySelector(".calm-toggle");
  var stored = null;
  try { stored = localStorage.getItem(CALM_KEY); } catch (e) {}
  var prefersReduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (stored === "on" || (stored === null && prefersReduced)) docEl.classList.add("calm");

  function isCalm() { return docEl.classList.contains("calm"); }

  function syncCalmToggle() {
    if (!calmToggle) return;
    calmToggle.setAttribute("aria-pressed", isCalm() ? "true" : "false");
    calmToggle.setAttribute("aria-label", isCalm() ? "Turn calm mode off" : "Turn calm mode on");
    calmToggle.title = isCalm() ? "Turn animations back on" : "Turn animations off for a calmer visit";
  }

  if (calmToggle) {
    syncCalmToggle();
    calmToggle.addEventListener("click", function () {
      docEl.classList.toggle("calm");
      try { localStorage.setItem(CALM_KEY, isCalm() ? "on" : "off"); } catch (e) {}
      syncCalmToggle();
    });
  }

  /* ---------- gently floating learning glyphs ---------- */
  var floatField = document.querySelector(".float-field");
  if (floatField) {
    var glyphs = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "+", "=", "×", "½", "★"];
    var glyphColors = ["#FF6B6B", "#12B5A5", "#7C6CF0", "#FFC53D", "#3EA8E0", "#FF8FAB"];
    for (var glyphIndex = 0; glyphIndex < 16; glyphIndex++) {
      var glyph = document.createElement("span");
      glyph.className = "float-num";
      glyph.textContent = glyphs[glyphIndex % glyphs.length];
      glyph.style.left = (Math.random() * 94) + "%";
      glyph.style.top = (Math.random() * 88) + "%";
      glyph.style.fontSize = (1.1 + Math.random() * 1.6) + "rem";
      glyph.style.color = glyphColors[glyphIndex % glyphColors.length];
      glyph.style.animationDelay = (Math.random() * -8) + "s";
      glyph.style.animationDuration = (7 + Math.random() * 4) + "s";
      floatField.appendChild(glyph);
    }
  }

  /* ---------- scroll reveal ---------- */
  document.documentElement.classList.add("js-ready");
  var revealEls = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && revealEls.length) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in-view");
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    revealEls.forEach(function (el) { io.observe(el); });
  } else {
    revealEls.forEach(function (el) { el.classList.add("in-view"); });
  }

  /* ---------- skills detail dialogs ---------- */
  var skillTriggers = document.querySelectorAll("[data-skill-dialog]");
  var skillDialogs = document.querySelectorAll(".skill-dialog");
  var returnFocus = null;

  skillTriggers.forEach(function (trigger) {
    trigger.addEventListener("click", function () {
      var dialog = document.getElementById(trigger.getAttribute("data-skill-dialog"));
      if (!dialog || typeof dialog.showModal !== "function") return;
      returnFocus = trigger;
      dialog.showModal();
      document.body.classList.add("dialog-open");
    });
  });

  skillDialogs.forEach(function (dialog) {
    dialog.querySelectorAll("[data-dialog-close]").forEach(function (closeButton) {
      closeButton.addEventListener("click", function () { dialog.close(); });
    });
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", function () {
      document.body.classList.remove("dialog-open");
      if (returnFocus && returnFocus.isConnected) returnFocus.focus();
      returnFocus = null;
    });
  });

  /* ---------- small celebration used after a successful form submission ---------- */
  function confetti(host) {
    if (isCalm()) return;
    var rect = host.getBoundingClientRect();
    var colors = ["#FF6B6B", "#12B5A5", "#FFC53D", "#7C6CF0", "#3EA8E0", "#FF8FAB"];
    for (var i = 0; i < 26; i++) {
      var piece = document.createElement("span");
      piece.className = "confetti-piece";
      piece.style.background = colors[i % colors.length];
      piece.style.left = (rect.left + rect.width / 2 + Math.random() * 140 - 70) + "px";
      piece.style.top = (rect.top + rect.height / 2 + Math.random() * 60 - 30) + "px";
      piece.style.animationDelay = (Math.random() * 0.25) + "s";
      document.body.appendChild(piece);
      (function (element) { setTimeout(function () { element.remove(); }, 1500); })(piece);
    }
  }

  /* ============================================================
     Contact form — friendly validation + Formspree submit
     ============================================================ */
  var form = document.getElementById("contactForm");
  if (form) {
    var status = document.getElementById("formStatus");

    /* Postcode is shown and required only when face-to-face is ticked */
    var online = document.getElementById("locationOnline");
    var faceToFace = document.getElementById("locationFaceToFace");
    var postcodeField = document.getElementById("postcodeField");
    var postcode = document.getElementById("postcode");
    if (online && faceToFace && postcodeField && postcode) {
      var syncPostcode = function () {
        var wantsFaceToFace = faceToFace.checked;
        postcodeField.hidden = !wantsFaceToFace;
        postcode.disabled = !wantsFaceToFace;
        postcode.required = wantsFaceToFace;
        if (!wantsFaceToFace) { postcode.value = ""; }
        online.setCustomValidity(
          online.checked || faceToFace.checked ? "" : "Please tick at least one location."
        );
      };
      online.addEventListener("change", syncPostcode);
      faceToFace.addEventListener("change", syncPostcode);
      form.addEventListener("reset", function () { setTimeout(syncPostcode, 0); });
      syncPostcode();
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!form.checkValidity()) {
        status.textContent = "Please fill in every field so Eva can reply. 🌷";
        status.className = "form-status err";
        form.reportValidity();
        return;
      }
      var btn = form.querySelector("button[type=submit]");
      btn.disabled = true;
      btn.textContent = "Sending…";
      status.textContent = "";
      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { "Accept": "application/json" }
      }).then(function (res) {
        if (res.ok) {
          status.textContent = "Thank you! Your message is on its way — Eva will be in touch soon. 💌";
          status.className = "form-status ok";
          form.reset();
          confetti(btn);
        } else {
          throw new Error("send failed");
        }
      }).catch(function () {
        status.textContent = "Hmm, something went wrong. Please try again in a moment.";
        status.className = "form-status err";
      }).finally(function () {
        btn.disabled = false;
        btn.innerHTML = "Send message <span class='arrow' aria-hidden='true'>➜</span>";
      });
    });
  }
})();

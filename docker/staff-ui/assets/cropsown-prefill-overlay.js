(function () {
  "use strict";
  if (window.__cropsownPrefillOverlay) return;
  window.__cropsownPrefillOverlay = true;

  var DIALOG = ".fixed.inset-0";
  var CROPSOWN_REGISTER = "6b06a95a-9a6c-5a33-a33d-c1625716c59c";
  var SECTIONS = [
    "0c0343ca-bac1-5c41-ae5d-72476fa21033", // Crop Planning
    "c9ee1d48-93b5-52d5-a8fc-280266a39c10", // Cultivation / Land Preparation
    "3392fa94-39fa-5eb7-891d-e593ab973e21", // Cultivation Cluster
    "ee41a5f0-a5b6-5a9c-a853-f5c728e4d4b2", // Sowing
    "c40d0a7c-9f31-5c89-9743-e83d6d6c7683", // Harvest
    "17cab427-590c-5db2-b6dc-5e224de97f65", // Infestation
    "62098187-a3f7-517a-be6d-b25da981153e"  // Cluster
  ];
  var FIELDS = {
    land:   { label: /^Land ID$/, tag: "input" },
    season: { label: /^Season$/, tag: "select" },
    crop:   { label: /^(Crop|Actual Crop Name|Crop type affected)$/, tag: "select" }
  };
  var nativeFetch = window.fetch;
  var cache = { rows: {}, submissionId: null };
  var STORE = "cropsownPrefillRows:";
  function localRows(key) {
    try { return JSON.parse(sessionStorage.getItem(STORE + key)) || []; } catch (e) { return []; }
  }
  function addLocalRow(key, row) {
    try { sessionStorage.setItem(STORE + key, JSON.stringify(localRows(key).concat(row))); } catch (e) { /* storage unavailable */ }
  }

  var m = location.pathname.match(/\/intake-form\/[^/]+\/submission\/([0-9a-fA-F-]{36})/);
  if (m) cache.submissionId = m[1];
  function registerRecordId() {
    var r = location.pathname.match(/\/register\/cropsown\/([^/?#]+)/);
    return r ? decodeURIComponent(r[1]) : null;
  }

  // the portal sends the submission id with every section save of a new form
  window.fetch = function (input, init) {
    try {
      var url = typeof input === "string" ? input : (input && input.url) || "";
      if (url.indexOf("/api/intake-form/save-intake-form-submission") > -1 && init && typeof init.body === "string") {
        var sent = JSON.parse(init.body);
        if (sent && sent.submission_id) { cache.submissionId = sent.submission_id; cache.rows = {}; }
      }
    } catch (e) { /* never break the portal */ }
    var p = nativeFetch.apply(this, arguments);
    try {
      var u = typeof input === "string" ? input : (input && input.url) || "";
      if (/save-intake-form-submission|register\/(update|save|create)|change-request\/create/.test(u)) {
        p.then(function () { cache.rows = {}; }).catch(function () {});
      }
    } catch (e) { /* never break the portal */ }
    return p;
  };

  function post(path, body) {
    return nativeFetch(path, {
      method: "POST", credentials: "same-origin",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) { return r.ok ? r.json() : null; });
  }

  // planning rows: objects carrying a land_id plus a season or a crop
  function extractRows(json) {
    var out = [];
    (function walk(o) {
      if (Array.isArray(o)) { o.forEach(walk); return; }
      if (!o || typeof o !== "object") return;
      if (o.land_id && (o.season || o.commodity)) {
        out.push({
          land: String(o.land_id).trim(),
          season: o.season ? String(o.season) : "",
          crop: o.commodity ? String(o.commodity) : ""
        });
      }
      Object.keys(o).forEach(function (k) { walk(o[k]); });
    })(json);
    return out;
  }
  function scopeKey() {
    var rid = registerRecordId();
    return rid ? "record:" + rid : cache.submissionId ? "sub:" + cache.submissionId : null;
  }
  function savedRows(key) {
    if (cache.rows[key]) return cache.rows[key];
    var rid = registerRecordId();
    var req = rid
      ? Promise.all(SECTIONS.map(function (sec) {
          return post("/api/register/section-data", {
            register_id: CROPSOWN_REGISTER, internal_record_id: rid, section_register_id: sec
          });
        }))
      : post("/api/intake-form/get-intake-form-submission", { submission_id: cache.submissionId });
    return (cache.rows[key] = req.then(extractRows).catch(function () { return []; }));
  }
  // every known row for this record: saved sections plus this page session's saves
  function sharedRows() {
    var key = scopeKey();
    if (!key) return Promise.resolve([]);
    return savedRows(key).then(function (rows) { return rows.concat(localRows(key)); });
  }
  function remember(dialog) {
    var key = scopeKey(), v = {};
    if (!key) return;
    Object.keys(FIELDS).forEach(function (f) {
      var el = control(dialog, FIELDS[f].label, FIELDS[f].tag);
      v[f] = el ? el.value.trim() : "";
    });
    if (v.land && (v.season || v.crop)) addLocalRow(key, v);
  }

  function labelOf(label) { return label.textContent.replace(/\s+/g, " ").replace(/\s*\*$/, "").trim(); }
  function control(dialog, labelRe, selector) {
    var labels = dialog.querySelectorAll("label");
    for (var i = 0; i < labels.length; i++) {
      if (labelRe.test(labelOf(labels[i]))) {
        var box = labels[i].parentElement;
        return box ? box.querySelector(selector) : null;
      }
    }
    return null;
  }
  function setValue(el, value) {
    var proto = el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  }
  function distinct(list) {
    var seen = {}, out = [];
    list.forEach(function (v) { if (v && !seen[v]) { seen[v] = true; out.push(v); } });
    return out;
  }
  function hasOption(select, value) {
    for (var i = 0; i < select.options.length; i++) if (select.options[i].value === value) return true;
    return false;
  }

  // Fill `el` with `value` unless the user has put something else there. A value
  // we set ourselves is tracked so a later Land ID change may replace it.
  function autoFill(el, value) {
    if (!value || el.__csUser) return false;
    if (el.value && el.value !== el.__csAuto) return false;
    if (el.tagName === "SELECT" && !hasOption(el, value)) return false;
    if (el.value === value) return false;
    el.__csAuto = value;
    setValue(el, value);
    return true;
  }

  function wire(dialog, rows) {
    var lands = distinct(rows.map(function (r) { return r.land; }));
    if (!lands.length) return;

    var listId = "cs-planned-lands";
    var list = document.getElementById(listId);
    if (!list) { list = document.createElement("datalist"); list.id = listId; document.body.appendChild(list); }
    list.innerHTML = "";
    lands.forEach(function (l) { var o = document.createElement("option"); o.value = l; list.appendChild(o); });

    // One field per pass: the portal builds each update from the form as of its
    // last render, so fields written in the same instant overwrite each other.
    function apply() {
      var land = control(dialog, FIELDS.land.label, FIELDS.land.tag);
      if (!land) return;
      land.setAttribute("list", listId);
      if (lands.length === 1 && autoFill(land, lands[0])) return;
      var matches = rows.filter(function (r) { return r.land === land.value.trim(); });
      var season = control(dialog, FIELDS.season.label, FIELDS.season.tag);
      var crop = control(dialog, FIELDS.crop.label, FIELDS.crop.tag);
      var seasons = distinct(matches.map(function (r) { return r.season; }));
      if (season && seasons.length === 1 && autoFill(season, seasons[0])) return;
      var crops = distinct(matches.map(function (r) { return r.crop; }));
      if (crop && crops.length === 1) autoFill(crop, crops[0]);
    }
    var queued = null;
    function schedule() {
      if (!queued) queued = setTimeout(function () { queued = null; apply(); }, 150);
    }
    function markUser(ev) { if (ev.isTrusted && ev.target) ev.target.__csUser = true; }
    dialog.addEventListener("input", markUser, true);
    dialog.addEventListener("change", markUser, true);
    dialog.addEventListener("input", schedule);
    dialog.addEventListener("change", schedule);
    new MutationObserver(schedule).observe(dialog, { childList: true, subtree: true });
    var timer = setInterval(function () {
      if (document.body.contains(dialog)) schedule(); else clearInterval(timer);
    }, 250);
    apply();
  }

  var wired = new WeakSet();
  function scan() {
    var dialogs = document.querySelectorAll(DIALOG);
    for (var i = 0; i < dialogs.length; i++) {
      var d = dialogs[i];
      if (wired.has(d)) continue;
      if (!d.querySelector("label")) continue; // not rendered yet
      wired.add(d);
      try {
        if (!control(d, FIELDS.land.label, FIELDS.land.tag)) continue;
        sharedRows().then(function (rows) { wire(this, rows); }.bind(d)).catch(function () {});
        d.addEventListener("click", function (ev) {
          var btn = ev.target.closest && ev.target.closest("button");
          if (btn && /^Save$/i.test(btn.textContent.trim())) remember(this);
        }.bind(d), true);
      } catch (e) { /* overlay must never break the dialog */ }
    }
  }
  new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true });
  scan();
})();

function savePref(fields) {
  var csrf = document.querySelector("input[name=csrf]");
  var root = document.documentElement;
  var body = new URLSearchParams();
  body.set("csrf", csrf ? csrf.value : "");
  Object.keys(fields).forEach(function (key) {
    body.set(key, fields[key]);
  });
  return fetch(root.dataset.prefs, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString()
  }).then(function (response) {
    return response.json().then(function (data) {
      if (!response.ok) {
        throw new Error(data && data.error ? data.error : "prefs");
      }
      return data;
    });
  });
}

function uiText(key, vars) {
  if (!uiText.bag) {
    var node = document.getElementById("i18n");
    try {
      uiText.bag = node ? JSON.parse(node.textContent) : {};
    } catch (error) {
      uiText.bag = {};
    }
  }
  var text = uiText.bag[key] || key;
  if (!vars) {
    return text;
  }
  Object.keys(vars).forEach(function (name) {
    text = text.split("{" + name + "}").join(String(vars[name]));
  });
  return text;
}

(function () {
  var root = document.documentElement;
  if (root.getAttribute("data-theme") !== "auto") {
    return;
  }
  var dayStart = 7;
  var dayEnd = 19;

  function themeAt(date) {
    var hour = date.getHours();
    return hour >= dayStart && hour < dayEnd ? "light" : "dark";
  }

  function apply(theme) {
    if (root.getAttribute("data-bs-theme") !== theme) {
      root.setAttribute("data-bs-theme", theme);
      document.body.classList.toggle("bg-body", theme === "dark");
      document.body.classList.toggle("bg-light", theme !== "dark");
    }
    var img = document.getElementById("chart");
    if (!img || !img.getAttribute("src")) {
      return;
    }
    var url = new URL(img.getAttribute("src"), location.origin);
    if (url.searchParams.get("theme") === theme) {
      return;
    }
    url.searchParams.set("theme", theme);
    img.src = url.pathname + url.search;
  }

  function nextChange(now) {
    var next = new Date(now.getTime());
    var hour = now.getHours();
    if (hour < dayStart) {
      next.setHours(dayStart, 0, 0, 0);
    } else if (hour < dayEnd) {
      next.setHours(dayEnd, 0, 0, 0);
    } else {
      next.setDate(next.getDate() + 1);
      next.setHours(dayStart, 0, 0, 0);
    }
    return next;
  }

  function arm() {
    var now = new Date();
    apply(themeAt(now));
    var wait = nextChange(now).getTime() - now.getTime();
    window.setTimeout(arm, Math.max(1000, wait));
  }

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      apply(themeAt(new Date()));
    }
  });
  arm();
})();

(function () {
  function place(button) {
    var menu = button.nextElementSibling;
    if (!menu) {
      return;
    }
    menu.style.transform = "";
    if (!menu.classList.contains("nav-panel")) {
      menu.style.marginTop = "";
      return;
    }
    var drop = button.parentElement.getBoundingClientRect();
    var note = document.querySelector(".slide-note");
    var target = note ? note.getBoundingClientRect().bottom + 8 : drop.bottom + 2;
    menu.style.marginTop = Math.max(2, Math.round(target - drop.bottom)) + "px";
    var width = Math.min(menu.classList.contains("nav-panel-wide") ? 832 : 576, document.documentElement.clientWidth - 16);
    var leftEdge = drop.right - width;
    if (leftEdge < 8) {
      menu.style.transform = "translateX(" + Math.round(8 - leftEdge) + "px)";
    }
  }

  document.querySelectorAll(".navbar [data-bs-toggle='dropdown']").forEach(function (button) {
    button.addEventListener("show.bs.dropdown", place.bind(null, button));
    button.addEventListener("hidden.bs.dropdown", function () {
      var menu = button.nextElementSibling;
      if (!menu) {
        return;
      }
      menu.style.marginTop = "";
      menu.style.transform = "";
    });
  });

  var openPanel = document.body.dataset.panel;
  if (openPanel) {
    var toggle = document.getElementById(openPanel + "-toggle");
    if (toggle) {
      bootstrap.Dropdown.getOrCreateInstance(toggle).show();
    }
  }

  var volumeControls = document.getElementById("volume-controls");
  var volumeMap = document.getElementById("volume-map");
  var volumeCaption = document.getElementById("volume-caption");
  var volumeFlat = document.getElementById("volume-flat");
  var volumeBand = document.getElementById("volume-band");
  var volumeSide = document.getElementById("volume-side");
  var volumeSessions = document.getElementById("volume-sessions");
  var volumeTitles = document.getElementById("volume-titles");
  var volumeSector = document.getElementById("volume-sector");
  var volumeGroup = document.getElementById("volume-group");
  var volumeCatalog = document.getElementById("volume-group-catalog");
  if (volumeControls && volumeMap && volumeSessions && volumeTitles && volumeSector && volumeGroup && volumeCatalog) {
    var volumeToken = 0;

    function clampVolume(kind, value) {
      if (kind === "sessions") {
        return Math.min(240, Math.max(1, value));
      }
      if (kind === "band") {
        var snapped = Math.round(value * 1000) / 1000;
        return Math.min(0.2, Math.max(0, snapped));
      }
      if (kind === "side") {
        var side = Math.round(value * 100) / 100;
        return Math.min(2, Math.max(0, side));
      }
      var snapped = Math.round(value / 10) * 10;
      return Math.min(500, Math.max(10, snapped));
    }

    function paintFrame(frame) {
      var node = document.createElement("div");
      node.className = "map-frame " + frame.level + " position-absolute";
      node.style.setProperty("--x", frame.x + "%");
      node.style.setProperty("--y", frame.y + "%");
      node.style.setProperty("--w", frame.w + "%");
      node.style.setProperty("--h", frame.h + "%");
      if (frame.title || frame.label) {
        node.title = frame.title || frame.label;
        var span = document.createElement("span");
        span.textContent = frame.label;
        node.append(span);
      }
      volumeMap.append(node);
    }

    function paintVolume(tiles, frames) {
      volumeMap.replaceChildren();
      (frames || []).forEach(paintFrame);
      tiles.forEach(function (tile) {
        var node = document.createElement("button");
        node.type = "button";
        node.className = "tile " + tile.kind + " " + tile.tone + (tile.scaled ? " scaled" : "") + " position-absolute overflow-hidden d-flex align-items-center justify-content-center text-center small lh-sm text-white border border-white";
        node.setAttribute("data-asset", tile.asset);
        node.title = tile.title;
        node.style.setProperty("--x", tile.x + "%");
        node.style.setProperty("--y", tile.y + "%");
        node.style.setProperty("--w", tile.w + "%");
        node.style.setProperty("--h", tile.h + "%");
        node.style.setProperty("--fs", (tile.fs || 11) + "px");
        var full = document.createElement("span");
        full.className = "full";
        full.append(document.createTextNode(tile.label), document.createElement("br"));
        var change = document.createElement("span");
        change.className = "chg text-nowrap";
        change.textContent = tile.change;
        full.append(change);
        if (tile.score) {
          full.append(document.createElement("br"));
          var score = document.createElement("span");
          score.className = "chg text-nowrap";
          score.textContent = tile.score;
          full.append(score);
        }
        var short = document.createElement("span");
        short.className = "short";
        short.append(document.createTextNode(tile.label));
        if (tile.score) {
          short.append(document.createElement("br"));
          var shortScore = document.createElement("span");
          shortScore.className = "chg text-nowrap";
          shortScore.textContent = tile.score;
          short.append(shortScore);
        }
        var line = document.createElement("span");
        line.className = "line text-nowrap";
        line.append(document.createTextNode(tile.label + " " + tile.change));
        if (tile.score) {
          line.append(document.createTextNode(" " + tile.score));
        }
        var mark = document.createElement("span");
        mark.className = "face";
        mark.append(document.createTextNode(tile.label), document.createElement("br"));
        var markChange = document.createElement("span");
        markChange.className = "chg text-nowrap";
        markChange.textContent = tile.change;
        mark.append(markChange);
        node.append(full, short, line, mark);
        volumeMap.append(node);
      });
      if (volumeMap.classList.contains("all-map")) {
        tiles.forEach(paintHair);
      }
    }

    function paintHair(tile) {
      var vertical = document.createElement("span");
      vertical.className = "tile-hair v";
      vertical.style.setProperty("--x", (tile.x + tile.w) + "%");
      vertical.style.setProperty("--y", tile.y + "%");
      vertical.style.setProperty("--h", tile.h + "%");
      var horizontal = document.createElement("span");
      horizontal.className = "tile-hair h";
      horizontal.style.setProperty("--x", tile.x + "%");
      horizontal.style.setProperty("--y", (tile.y + tile.h) + "%");
      horizontal.style.setProperty("--w", tile.w + "%");
      volumeMap.append(vertical, horizontal);
    }

    function volumeOrder() {
      var active = volumeControls.querySelector("[data-order].active");
      return active ? active.getAttribute("data-order") : "rank";
    }

    function volumeScope() {
      var active = volumeControls.querySelector("[data-scope].active");
      return active ? active.getAttribute("data-scope") : "sector";
    }

    function volumeDivide() {
      var active = volumeControls.querySelector("[data-divide].active");
      return active ? active.getAttribute("data-divide") : "off";
    }

    function setVolumeDivide(divide) {
      volumeControls.querySelectorAll("[data-divide]").forEach(function (button) {
        button.classList.toggle("active", button.getAttribute("data-divide") === divide);
      });
      syncScale();
    }

    function volumeScale() {
      var active = volumeControls.querySelector("[data-scale].active");
      return active ? active.getAttribute("data-scale") : "off";
    }

    function setVolumeScale(scale) {
      volumeControls.querySelectorAll("[data-scale]").forEach(function (button) {
        button.classList.toggle("active", button.getAttribute("data-scale") === scale);
      });
      syncScale();
    }

    function syncScale() {
      var wrap = document.getElementById("volume-scale-wrap");
      var show = volumeScope() === "all";
      if (wrap) {
        wrap.classList.toggle("d-none", !show);
      }
      if (volumeMap) {
        volumeMap.classList.toggle("scale", show && volumeScale() === "on");
      }
    }

    function setVolumeOrder(order) {
      volumeControls.querySelectorAll("[data-order]").forEach(function (button) {
        button.classList.toggle("active", button.getAttribute("data-order") === order);
      });
    }

    function setVolumeScope(scope) {
      var all = scope === "all";
      volumeControls.querySelectorAll("[data-scope]").forEach(function (button) {
        button.classList.toggle("active", button.getAttribute("data-scope") === scope);
      });
      var sectorWrap = document.getElementById("volume-sector-wrap");
      var groupWrap = document.getElementById("volume-group-wrap");
      var orderWrap = document.getElementById("volume-order-wrap");
      var sessionsWrap = document.getElementById("volume-sessions-wrap");
      var titlesWrap = document.getElementById("volume-titles-wrap");
      if (sectorWrap) {
        sectorWrap.classList.toggle("d-none", all);
      }
      if (groupWrap) {
        groupWrap.classList.toggle("d-none", all);
      }
      if (orderWrap) {
        orderWrap.classList.toggle("d-none", all);
      }
      if (sessionsWrap) {
        sessionsWrap.classList.toggle("d-none", all);
      }
      if (titlesWrap) {
        titlesWrap.classList.toggle("d-none", all);
      }
      if (volumeMap) {
        volumeMap.classList.toggle("all-map", all);
      }
      var modeCol = document.getElementById("volume-mode");
      if (modeCol) {
        modeCol.classList.toggle("col-lg-2", all);
        modeCol.classList.toggle("col-lg-3", !all);
      }
      var sideWrap = document.getElementById("volume-side-wrap");
      if (sideWrap) {
        sideWrap.classList.toggle("d-none", !all);
      }
      var divideWrap = document.getElementById("volume-divide-wrap");
      if (divideWrap) {
        divideWrap.classList.toggle("d-none", !all);
      }
      var bandWrap = document.getElementById("volume-band-wrap");
      var mode = document.getElementById("volume-mode");
      var filtersRow = document.getElementById("volume-filters-row");
      if (bandWrap && mode && sectorWrap) {
        if (all) {
          mode.parentElement.appendChild(bandWrap);
          if (sideWrap) {
            mode.parentElement.appendChild(sideWrap);
          }
          if (divideWrap) {
            mode.parentElement.appendChild(divideWrap);
          }
          var scaleWrap = document.getElementById("volume-scale-wrap");
          if (scaleWrap) {
            mode.parentElement.appendChild(scaleWrap);
          }
        } else {
          sectorWrap.parentElement.appendChild(bandWrap);
        }
      }
      if (filtersRow) {
        filtersRow.classList.toggle("d-none", all);
      }
      syncScale();
    }

    var volumeSaved = {
      sessions: volumeSessions.value,
      titles: volumeTitles.value,
      sector: volumeSector.value,
      group: volumeGroup.value,
      order: volumeOrder(),
      scope: volumeScope(),
      band: volumeBand ? volumeBand.value : "",
      side: volumeSide ? volumeSide.value : "",
      divide: volumeDivide(),
      scale: volumeScale()
    };

    function fillGroups(sector, groupValue) {
      volumeGroup.replaceChildren();
      var all = document.createElement("option");
      all.value = "";
      all.textContent = volumeGroup.getAttribute("data-all") || "";
      volumeGroup.append(all);
      [].forEach.call(volumeCatalog.children, function (group) {
        if (group.tagName !== "OPTGROUP") {
          return;
        }
        var code = group.getAttribute("data-sector");
        if (sector && code !== sector) {
          return;
        }
        var copy = group.cloneNode(true);
        [].forEach.call(copy.children, function (option) {
          option.setAttribute("data-sector", code);
        });
        volumeGroup.append(copy);
      });
      var wanted = groupValue || "";
      volumeGroup.value = wanted;
      if (volumeGroup.value !== wanted) {
        volumeGroup.value = "";
      }
    }

    function applyClass(value) {
      var sector = "";
      var group = "";
      if (value.indexOf("s:") === 0) {
        sector = value.slice(2);
      } else if (value.indexOf("u:") === 0) {
        group = value;
        sector = value.slice(2).split("|")[0];
      }
      if (sector && !volumeCatalog.querySelector('[data-sector="' + CSS.escape(sector) + '"]')) {
        sector = "";
        group = "";
      }
      volumeSector.value = sector;
      fillGroups(sector, group);
    }

    function composeClass() {
      if (volumeGroup.value) {
        return volumeGroup.value;
      }
      if (volumeSector.value) {
        return "s:" + volumeSector.value;
      }
      return "";
    }

    function restoreVolume() {
      volumeSessions.value = volumeSaved.sessions;
      volumeTitles.value = volumeSaved.titles;
      if (volumeBand) {
        volumeBand.value = volumeSaved.band;
      }
      if (volumeSide) {
        volumeSide.value = volumeSaved.side;
      }
      volumeSector.value = volumeSaved.sector;
      fillGroups(volumeSaved.sector, volumeSaved.group);
      setVolumeOrder(volumeSaved.order);
      setVolumeScope(volumeSaved.scope);
      setVolumeDivide(volumeSaved.divide);
      setVolumeScale(volumeSaved.scale);
    }

    var volumeWait = document.getElementById("volume-wait");

    function setVolumeBusy(busy) {
      if (!volumeWait) {
        return;
      }
      volumeWait.classList.toggle("d-none", !busy);
      volumeWait.classList.toggle("d-flex", busy);
    }

    function pushVolume() {
      var token = ++volumeToken;
      setVolumeBusy(true);
      var csrf = document.querySelector("input[name=csrf]");
      var body = new URLSearchParams();
      body.set("csrf", csrf ? csrf.value : "");
      body.set("return_days", volumeSessions.value);
      body.set("names", volumeTitles.value);
      body.set("stable_band", volumeBand ? volumeBand.value : "");
      body.set("min_side", volumeSide ? volumeSide.value : "");
      body.set("volume_class", composeClass());
      body.set("order", volumeOrder());
      body.set("scope", volumeScope());
      body.set("divide", volumeDivide());
      body.set("scale", volumeScale());
      fetch(volumeControls.dataset.volume, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString()
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("volume");
          }
          return response.json();
        })
        .then(function (data) {
          if (token !== volumeToken) {
            return;
          }
          volumeSessions.value = String(data.sessions);
          volumeTitles.value = String(data.count);
          applyClass(data.group || "");
          volumeSaved.sessions = volumeSessions.value;
          volumeSaved.titles = volumeTitles.value;
          volumeSaved.sector = volumeSector.value;
          volumeSaved.group = volumeGroup.value;
          volumeSaved.order = data.order || volumeOrder();
          volumeSaved.scope = data.scope || volumeScope();
          volumeSaved.divide = data.divide || volumeDivide();
          volumeSaved.scale = data.scale || volumeScale();
          setVolumeOrder(volumeSaved.order);
          setVolumeScope(volumeSaved.scope);
          setVolumeDivide(volumeSaved.divide);
          setVolumeScale(volumeSaved.scale);
          var prefSessions = document.getElementById("pref-return");
          var prefTitles = document.getElementById("pref-names");
          if (prefSessions) {
            prefSessions.value = volumeSessions.value;
          }
          if (prefTitles) {
            prefTitles.value = volumeTitles.value;
          }
          if (volumeBand && data.band) {
            volumeBand.value = data.band;
            volumeSaved.band = data.band;
          }
          if (volumeSide && data.side) {
            volumeSide.value = data.side;
            volumeSaved.side = data.side;
          }
          var prefBand = document.getElementById("pref-band");
          if (prefBand && data.band) {
            prefBand.value = data.band;
          }
          if (volumeFlat && data.flat) {
            volumeFlat.textContent = data.flat;
          }
          if (volumeCaption) {
            volumeCaption.textContent = data.caption;
          }
          paintVolume(data.tiles || [], data.frames || []);
          setVolumeBusy(false);
          remember("volume");
        })
        .catch(function () {
          if (token === volumeToken) {
            restoreVolume();
            setVolumeBusy(false);
          }
        });
    }

    function commitVolume(input, kind) {
      var raw = String(input.value).trim().replace(",", ".");
      var value = Number(raw);
      if (!raw || !isFinite(value)) {
        input.value = kind === "sessions" ? volumeSaved.sessions : kind === "band" ? volumeSaved.band : kind === "side" ? volumeSaved.side : volumeSaved.titles;
        return;
      }
      input.value = String(clampVolume(kind, value));
      var saved = kind === "sessions" ? volumeSaved.sessions : kind === "band" ? volumeSaved.band : kind === "side" ? volumeSaved.side : volumeSaved.titles;
      if (input.value !== saved) {
        pushVolume();
      }
    }

    function bindCommit(input, kind) {
      input.addEventListener("change", function () {
        commitVolume(input, kind);
      });
      input.addEventListener("keydown", function (event) {
        if (event.key !== "Enter") {
          return;
        }
        event.preventDefault();
        input.blur();
      });
    }

    bindCommit(volumeSessions, "sessions");
    bindCommit(volumeTitles, "titles");
    if (volumeBand) {
      bindCommit(volumeBand, "band");
    }
    if (volumeSide) {
      bindCommit(volumeSide, "side");
    }

    volumeControls.querySelectorAll("[data-volume-step]").forEach(function (button) {
      button.addEventListener("click", function () {
        var kind = button.getAttribute("data-volume-step");
        var input = kind === "sessions" ? volumeSessions : kind === "band" ? volumeBand : kind === "side" ? volumeSide : volumeTitles;
        var step = kind === "sessions" ? 1 : kind === "band" ? 0.001 : kind === "side" ? 0.01 : 10;
        var next = clampVolume(kind, Number(input.value) + step * Number(button.getAttribute("data-dir")));
        if (String(next) === input.value) {
          return;
        }
        input.value = String(next);
        pushVolume();
      });
    });
    volumeSector.addEventListener("change", function () {
      fillGroups(volumeSector.value, "");
      pushVolume();
    });
    volumeGroup.addEventListener("change", function () {
      var option = volumeGroup.options[volumeGroup.selectedIndex];
      var sector = option ? option.getAttribute("data-sector") : "";
      if (!volumeGroup.value) {
        volumeSector.value = "";
        fillGroups("", "");
      } else if (sector && volumeSector.value !== sector) {
        volumeSector.value = sector;
        fillGroups(sector, option.value);
      }
      pushVolume();
    });
    volumeControls.querySelectorAll("[data-order]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (button.classList.contains("active")) {
          return;
        }
        setVolumeOrder(button.getAttribute("data-order"));
        pushVolume();
      });
    });
    volumeControls.querySelectorAll("[data-divide]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (button.classList.contains("active")) {
          return;
        }
        setVolumeDivide(button.getAttribute("data-divide"));
        pushVolume();
      });
    });
    volumeControls.querySelectorAll("[data-scale]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (button.classList.contains("active")) {
          return;
        }
        setVolumeScale(button.getAttribute("data-scale"));
        pushVolume();
      });
    });
    volumeControls.querySelectorAll("[data-scope]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (button.classList.contains("active")) {
          return;
        }
        setVolumeScope(button.getAttribute("data-scope"));
        pushVolume();
      });
    });
  }

  var frameEl = document.getElementById("chart-frame");
  var img = document.getElementById("chart");
  var svg = document.getElementById("chart-svg");
  var select = document.getElementById("pref-focus");
  if (!img || !select || !frameEl) {
    return;
  }
  function isVector() {
    return frameEl.dataset.render === "vector";
  }

  function applyRender(mode) {
    frameEl.dataset.render = mode;
    img.classList.toggle("d-none", mode === "vector");
    svg.classList.toggle("d-none", mode !== "vector");
    var hit = document.getElementById("chart-hit");
    if (hit) {
      hit.classList.toggle("d-none", mode === "vector");
    }
    drawn = "";
    seriesKey = "";
  }
  var NS = "http://www.w3.org/2000/svg";

  function chosen(name) {
    var button = document.querySelector("[data-" + name + "].active");
    return button ? button.getAttribute("data-" + name) : "";
  }

  function frame() {
    var width = frameEl.clientWidth;
    width = Math.round(width);
    var top = frameEl.getBoundingClientRect().top;
    var room = Math.round(window.innerHeight - top - 28);
    if (room < 280) {
      room = 280;
    }
    var height = Math.min(Math.round(width * 8.2 / 14.5), room);
    if (height < 280) {
      height = 280;
    }
    return { w: width, h: height };
  }

  function chartUrl(box) {
    var url = new URL(img.dataset.history, location.origin);
    url.searchParams.set("asset", select.value);
    url.searchParams.set("period", chosen("period"));
    url.searchParams.set("chart", chosen("chart"));
    url.searchParams.set("w", String(box.w));
    url.searchParams.set("h", String(box.h));
    url.searchParams.set("scale", document.documentElement.dataset.scale || "100");
    url.searchParams.set("theme", document.documentElement.getAttribute("data-bs-theme") || "light");
    url.searchParams.set("weight", getComputedStyle(document.documentElement).getPropertyValue("--bs-body-font-weight").trim() || "400");
    return url.pathname + url.search;
  }

  function remember(view) {
    var params = new URLSearchParams(location.search);
    params.set("view", view);
    params.set("asset", select.value);
    params.set("period", chosen("period"));
    params.set("chart", chosen("chart"));
    var orderButton = document.querySelector("[data-order].active");
    if (orderButton) {
      params.set("order", orderButton.getAttribute("data-order"));
    }
    var scopeButton = document.querySelector("[data-scope].active");
    if (scopeButton) {
      params.set("scope", scopeButton.getAttribute("data-scope"));
    }
    params.delete("ok");
    params.delete("err");
    history.replaceState(null, "", location.pathname + "?" + params.toString());
  }

  var drawn = "";
  var statsBox = document.getElementById("stats");
  var statsKey = select.value + "|" + chosen("period");

  function fillStats(data) {
    ["change", "last", "low", "high", "sessions"].forEach(function (name) {
      var node = statsBox.querySelector("[data-stat='" + name + "']");
      if (node) {
        node.textContent = data[name];
      }
    });
    var change = statsBox.querySelector("[data-stat='change']");
    change.classList.remove("text-success", "text-danger", "text-body");
    change.classList.add(data.tone === "success" ? "text-success" : data.tone === "danger" ? "text-danger" : "text-body");
  }

  function loadStats() {
    if (!statsBox) {
      return;
    }
    var key = select.value + "|" + chosen("period");
    if (key === statsKey) {
      return;
    }
    var url = new URL(statsBox.dataset.stats, location.origin);
    url.searchParams.set("asset", select.value);
    url.searchParams.set("period", chosen("period"));
    fetch(url.pathname + url.search, { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("stats");
        }
        return response.json();
      })
      .then(function (data) {
        if (select.value + "|" + chosen("period") !== key) {
          return;
        }
        statsKey = key;
        fillStats(data);
      })
      .catch(function () {});
  }

  var hitLayer = document.getElementById("chart-hit");
  var hitsDrawn = "";
  var note = document.createElement("div");
  note.className = "position-absolute z-3 d-none pe-none bg-body text-body border rounded-2 px-2 py-1 shadow";
  if (hitLayer && hitLayer.parentElement) {
    hitLayer.parentElement.appendChild(note);
  }

  function showNote(zone, event) {
    var lines = zone._lines || [];
    if (!lines.length) {
      note.classList.add("d-none");
      return;
    }
    note.replaceChildren();
    lines.forEach(function (line) {
      var row = document.createElement("div");
      row.textContent = line;
      note.appendChild(row);
    });
    note.classList.remove("d-none");
    var box = frameEl.getBoundingClientRect();
    var x = event.clientX - box.left + 14;
    var y = event.clientY - box.top + 14;
    if (x + note.offsetWidth > box.width - 8) {
      x = event.clientX - box.left - note.offsetWidth - 14;
    }
    if (y + note.offsetHeight > box.height - 8) {
      y = event.clientY - box.top - note.offsetHeight - 14;
    }
    note.style.left = Math.max(4, x) + "px";
    note.style.top = Math.max(4, y) + "px";
  }

  if (hitLayer) {
    hitLayer.addEventListener("mousemove", function (event) {
      if (event.target && event.target._lines) {
        showNote(event.target, event);
      }
    });
    hitLayer.addEventListener("mouseleave", function () {
      note.classList.add("d-none");
    });
  }
  if (svg) {
    svg.addEventListener("mouseleave", function () {
      note.classList.add("d-none");
    });
  }

  function paintHits() {
    if (!hitLayer) {
      return;
    }
    var url = new URL(hitLayer.dataset.hits, location.origin);
    url.searchParams.set("asset", select.value);
    url.searchParams.set("period", chosen("period"));
    url.searchParams.set("chart", chosen("chart"));
    var key = url.pathname + url.search;
    if (key === hitsDrawn) {
      return;
    }
    hitsDrawn = key;
    fetch(key, { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("hits");
        }
        return response.json();
      })
      .then(function (data) {
        if (hitsDrawn !== key) {
          return;
        }
        hitLayer.replaceChildren();
        (data.hits || []).forEach(function (hit) {
          var zone = document.createElement("div");
          zone.className = "position-absolute top-0 h-100";
          zone.style.left = hit.x + "%";
          zone.style.width = hit.w + "%";
          zone._lines = hit.lines || [];
          zone.addEventListener("pointermove", function (event) {
            showNote(zone, event);
          });
          hitLayer.appendChild(zone);
        });
      })
      .catch(function () {
        if (hitsDrawn === key) {
          hitLayer.replaceChildren();
        }
      });
  }

  function svgEl(name, attrs) {
    var node = document.createElementNS(NS, name);
    Object.keys(attrs).forEach(function (key) {
      node.setAttribute(key, attrs[key]);
    });
    return node;
  }

  function priceText(value) {
    var text = Number(value).toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
    return text || "0";
  }

  function axisTicks(low, high) {
    var span = high - low;
    if (!(span > 0)) {
      return [low];
    }
    var raw = span / 4;
    var mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var norm = raw / mag;
    var step = (norm >= 5 ? 5 : norm >= 2 ? 2 : 1) * mag;
    var start = Math.ceil(low / step) * step;
    var ticks = [];
    var guard = 0;
    for (var value = start; value < high && guard < 6; value += step) {
      if (value > low) {
        ticks.push(value);
      }
      guard += 1;
    }
    if (!ticks.length) {
      ticks.push((low + high) / 2);
    }
    return ticks;
  }

  function dayNumber(iso) {
    var parts = iso.split("-");
    return Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])) / 86400000;
  }

  function sessionTone(point, previous) {
    var close = Number(point.c);
    var rising;
    if (point.o !== null && point.o !== undefined) {
      rising = close >= Number(point.o);
    } else if (previous === null) {
      rising = true;
    } else {
      rising = close >= previous;
    }
    return rising ? "var(--bs-success)" : "var(--bs-danger)";
  }

  var seriesToken = 0;
  var seriesKey = "";
  var seriesData = null;

  function drawSvg(data, box) {
    if (!svg) {
      return;
    }
    var width = box.w;
    var height = box.h;
    var span = Math.sqrt(width * height);
    var tick = 13 + (span - 640) * (6 / 1000);
    var scale = Number(document.documentElement.dataset.scale) || 100;
    tick = Math.max(12, Math.min(19, tick)) * scale / 100;
    var weight = Number(getComputedStyle(document.documentElement).getPropertyValue("--bs-body-font-weight")) || 400;
    var titleWeight = Math.max(500, weight);
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("font-family", "inherit");
    svg.style.height = height + "px";
    svg.replaceChildren();
    svg.setAttribute("aria-label", data.title || uiText("history.alt", { asset: select.value }));
    var points = data.points || [];
    if (!points.length) {
      var empty = svgEl("text", {
        x: width / 2,
        y: height / 2,
        "text-anchor": "middle",
        fill: "var(--bs-body-color)",
        "font-size": tick + "px",
        "font-weight": String(titleWeight)
      });
      empty.textContent = data.title;
      svg.appendChild(empty);
      return;
    }
    var lows = [];
    var highs = [];
    points.forEach(function (point) {
      if (data.draw === "candle") {
        lows.push(Number(point.l));
        highs.push(Number(point.h));
      } else {
        lows.push(Number(point.c));
        highs.push(Number(point.c));
      }
    });
    var low = Math.min.apply(null, lows);
    var high = Math.max.apply(null, highs);
    var range = high - low;
    var padTop = range * 0.04 || high * 0.004 || 1;
    var padBottom = range * 0.16 || high * 0.008 || 1;
    low -= padBottom;
    high += padTop;
    var ticks = axisTicks(low, high);
    var probe = svgEl("text", {
      "font-size": tick + "px",
      "font-weight": String(weight)
    });
    var labelWidth = 0;
    ticks.forEach(function (value) {
      probe.textContent = priceText(value);
      svg.appendChild(probe);
      labelWidth = Math.max(labelWidth, probe.getBBox().width);
      probe.remove();
    });
    if (!labelWidth) {
      labelWidth = priceText(high).length * tick * 0.56;
    }
    var left = Math.ceil(labelWidth + 14);
    var right = width - 12;
    var top = 8;
    var volumeH = Math.max(32, Math.round(height * 0.12));
    var dateBand = points.length > 12 ? tick * 3.2 : tick * 1.7;
    var plotBottom = height - 10 - volumeH - dateBand;
    var plotW = Math.max(40, right - left);
    var plotH = Math.max(40, plotBottom - top);
    var xs = data.draw === "candle"
      ? points.map(function (_point, index) { return index; })
      : points.map(function (point) { return dayNumber(point.d); });
    var margin = data.draw === "candle" ? 0.02 : 0.03;
    var xSpan = xs[xs.length - 1] - xs[0];
    var viewLo = xSpan === 0 ? xs[0] - 1 : xs[0] - margin * xSpan;
    var viewHi = xSpan === 0 ? xs[0] + 1 : xs[xs.length - 1] + margin * xSpan;
    var view = viewHi - viewLo;

    function xAt(index) {
      return left + (xs[index] - viewLo) / view * plotW;
    }
    function yAt(value) {
      return plotBottom - (value - low) / (high - low) * plotH;
    }

    if (data.draw === "candle") {
      var bodyW = Math.max(1, 0.6 / view * plotW);
      points.forEach(function (point, index) {
        var color = sessionTone(point, null);
        var x = xAt(index);
        svg.appendChild(svgEl("line", {
          x1: x, x2: x, y1: yAt(point.h), y2: yAt(point.l),
          stroke: color, "stroke-width": "1.25"
        }));
        var open = Number(point.o);
        var close = Number(point.c);
        var bodyTop = yAt(Math.max(open, close));
        var bodyHeight = Math.max(1, Math.abs(yAt(open) - yAt(close)));
        svg.appendChild(svgEl("rect", {
          x: x - bodyW / 2,
          y: bodyTop,
          width: bodyW,
          height: bodyHeight,
          fill: color
        }));
      });
    } else {
      var commands = points.map(function (point, index) {
        return (index ? "L" : "M") + xAt(index).toFixed(2) + " " + yAt(point.c).toFixed(2);
      }).join(" ");
      svg.appendChild(svgEl("path", {
        d: commands,
        fill: "none",
        stroke: "var(--bs-primary)",
        "stroke-width": "2.25",
        "stroke-linejoin": "round",
        "stroke-linecap": "round"
      }));
      if (points.length <= 40) {
        points.forEach(function (point, index) {
          svg.appendChild(svgEl("circle", {
            cx: xAt(index),
            cy: yAt(point.c),
            r: Math.max(3, tick * 0.28),
            fill: "var(--bs-primary)",
            stroke: "var(--bs-body-bg)",
            "stroke-width": "1.4"
          }));
        });
      }
    }

    var step = points.length <= 12 ? 1 : Math.max(1, Math.floor(points.length / 8));
    var dateY = plotBottom + tick + 8;
    for (var index = 0; index < points.length; index += step) {
      var date = svgEl("text", {
        x: xAt(index),
        y: dateY,
        fill: "var(--bs-body-color)",
        "font-size": tick + "px",
        "font-weight": String(weight),
        "text-anchor": points.length > 12 ? "end" : "middle"
      });
      date.textContent = points[index].label;
      if (points.length > 12) {
        date.setAttribute("transform", "rotate(-30 " + xAt(index) + " " + dateY + ")");
      }
      svg.appendChild(date);
    }

    var amounts = points.map(function (point) { return Number(point.v) || 0; });
    var peak = Math.max.apply(null, amounts);
    var volumeTop = height - 8 - volumeH;
    var volumeBottom = height - 8;
    svg.appendChild(svgEl("line", {
      x1: left, y1: volumeBottom, x2: right, y2: volumeBottom,
      stroke: "var(--bs-border-color)", "stroke-width": "1"
    }));
    if (peak > 0) {
      var unit = data.draw === "candle" ? 0.6 : 0.72;
      var barW = Math.max(1, unit / view * plotW);
      var previous = null;
      points.forEach(function (point, i) {
        var amount = amounts[i];
        var barH = amount / peak * (volumeH - 4);
        svg.appendChild(svgEl("rect", {
          x: xAt(i) - barW / 2,
          y: volumeBottom - barH,
          width: barW,
          height: Math.max(0, barH),
          fill: sessionTone(point, previous)
        }));
        previous = Number(point.c);
      });
    }

    ticks.forEach(function (value) {
      var y = yAt(value);
      svg.appendChild(svgEl("line", {
        x1: left,
        x2: right,
        y1: y,
        y2: y,
        stroke: "var(--bs-border-color)",
        "stroke-width": "1"
      }));
      var label = svgEl("text", {
        x: left - 8,
        y: y + tick * 0.35,
        "text-anchor": "end",
        fill: "var(--bs-body-color)",
        "font-size": tick + "px",
        "font-weight": String(weight)
      });
      label.textContent = priceText(value);
      svg.appendChild(label);
    });
    svg.appendChild(svgEl("line", {
      x1: left, y1: top, x2: left, y2: plotBottom,
      stroke: "var(--bs-border-color)", "stroke-width": "1"
    }));
    svg.appendChild(svgEl("line", {
      x1: left, y1: plotBottom, x2: right, y2: plotBottom,
      stroke: "var(--bs-border-color)", "stroke-width": "1"
    }));

    points.forEach(function (point, index) {
      var start = index === 0 ? left : (xAt(index - 1) + xAt(index)) / 2;
      var end = index + 1 === points.length ? right : (xAt(index) + xAt(index + 1)) / 2;
      var zone = svgEl("rect", {
        x: start,
        y: top,
        width: Math.max(1, end - start),
        height: volumeBottom - top,
        fill: "none",
        "pointer-events": "all"
      });
      zone._lines = point.lines || [];
      zone.addEventListener("pointermove", function (event) {
        showNote(zone, event);
      });
      svg.appendChild(zone);
    });
  }

  function seriesUrl() {
    var url = new URL(frameEl.dataset.series, location.origin);
    url.searchParams.set("asset", select.value);
    url.searchParams.set("period", chosen("period"));
    url.searchParams.set("chart", chosen("chart"));
    return url.pathname + url.search;
  }

  function paintVector(box) {
    var key = seriesUrl();
    if (key === seriesKey && seriesData) {
      drawSvg(seriesData, box);
      return;
    }
    seriesKey = key;
    var token = ++seriesToken;
    fetch(key, { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("serie");
        }
        return response.json();
      })
      .then(function (data) {
        if (token !== seriesToken) {
          return;
        }
        seriesData = data;
        drawSvg(data, frame());
      })
      .catch(function () {
        if (token !== seriesToken) {
          return;
        }
        drawSvg({ title: uiText("chart.unavailable"), points: [] }, frame());
      });
  }

  function paint() {
    var box = frame();
    if (box.w < 200) {
      return;
    }
    if (isVector()) {
      paintVector(box);
    } else {
      var next = chartUrl(box);
      if (next !== drawn) {
        drawn = next;
        img.src = next;
      }
      img.alt = uiText("history.alt", { asset: select.value });
      paintHits();
    }
    remember("history");
    loadStats();
  }

  function restoreGroup(group, name, saved) {
    group.querySelectorAll("[data-" + name + "]").forEach(function (other) {
      other.classList.toggle("active", other.getAttribute("data-" + name) === saved);
    });
  }

  select.addEventListener("change", function () {
    var previous = select.getAttribute("data-saved") || "";
    if (select.value === previous) {
      return;
    }
    savePref({ focus_asset: select.value }).then(function (data) {
      select.value = data.values.focus_asset;
      select.setAttribute("data-saved", select.value);
      paint();
    }).catch(function () {
      select.value = previous;
    });
  });

  document.querySelectorAll("[data-period], [data-chart]").forEach(function (button) {
    button.addEventListener("click", function () {
      var name = button.hasAttribute("data-period") ? "period" : "chart";
      var key = name === "period" ? "history_period" : "chart_type";
      var group = button.parentElement;
      var previous = group.getAttribute("data-saved") || "";
      var value = button.getAttribute("data-" + name);
      restoreGroup(group, name, value);
      if (value === previous) {
        return;
      }
      var fields = {};
      fields[key] = value;
      savePref(fields).then(function (data) {
        group.setAttribute("data-saved", data.values[key]);
        restoreGroup(group, name, data.values[key]);
        paint();
      }).catch(function () {
        restoreGroup(group, name, previous);
      });
    });
  });

  document.querySelectorAll("[data-render]").forEach(function (button) {
    button.addEventListener("click", function () {
      var group = button.parentElement;
      var previous = group.getAttribute("data-saved") || "";
      var value = button.getAttribute("data-render");
      restoreGroup(group, "render", value);
      if (value === previous) {
        return;
      }
      savePref({ chart_render: value }).then(function (data) {
        group.setAttribute("data-saved", data.values.chart_render);
        applyRender(data.values.chart_render);
        paint();
      }).catch(function () {
        restoreGroup(group, "render", previous);
      });
    });
  });

  document.addEventListener("prefs-applied", function (event) {
    var key = event.detail && event.detail.key;
    if (key === "ui_scale" || key === "ui_weight" || key === "ui_theme") {
      drawn = "";
      seriesKey = "";
      paint();
    }
  });

  var volumeTab = document.getElementById("volume-tab");
  var historyTab = document.getElementById("history-tab");
  if (volumeTab) {
    volumeTab.addEventListener("shown.bs.tab", function () {
      remember("volume");
      savePref({ page_view: "volume" });
    });
  }
  if (historyTab) {
    historyTab.addEventListener("shown.bs.tab", function () {
      savePref({ page_view: "history" });
      paint();
    });
  }

  function openVolumeTile(asset) {
    if (!asset) {
      return;
    }
    var previous = select.value;
    var exists = false;
    [].forEach.call(select.options, function (option) {
      if (option.value === asset) {
        exists = true;
      }
    });
    if (!exists) {
      var extra = document.createElement("option");
      extra.value = asset;
      extra.textContent = asset;
      select.add(extra);
    }
    select.value = asset;
    var chartGroup = document.querySelector("[data-chart]");
    chartGroup = chartGroup ? chartGroup.parentElement : null;
    var previousChart = chartGroup ? chartGroup.getAttribute("data-saved") : "";
    if (chartGroup) {
      restoreGroup(chartGroup, "chart", "candle");
    }
    savePref({ focus_asset: asset, chart_type: "candle" }).then(function (data) {
      select.value = data.values.focus_asset;
      select.setAttribute("data-saved", select.value);
      if (chartGroup) {
        chartGroup.setAttribute("data-saved", data.values.chart_type);
      }
      if (historyTab && !historyTab.classList.contains("active")) {
        bootstrap.Tab.getOrCreateInstance(historyTab).show();
        return;
      }
      paint();
    }).catch(function () {
      select.value = previous;
      if (chartGroup) {
        restoreGroup(chartGroup, "chart", previousChart);
      }
    });
  }

  if (volumeMap) {
    volumeMap.addEventListener("click", function (event) {
      var tile = event.target.closest("[data-asset]");
      if (!tile || !volumeMap.contains(tile)) {
        return;
      }
      openVolumeTile(tile.getAttribute("data-asset"));
    });
  }

  var timer = 0;
  function schedule() {
    window.clearTimeout(timer);
    timer = window.setTimeout(paint, 150);
  }
  window.addEventListener("resize", schedule);
  if (window.ResizeObserver && img.parentElement) {
    new ResizeObserver(schedule).observe(img.parentElement);
  }
  if (img.closest(".tab-pane.active") || img.offsetParent !== null) {
    paint();
  }
})();

(function () {
  function closeMenus() {
    document.querySelectorAll(".pref-menu.show").forEach(function (menu) {
      menu.classList.remove("show");
    });
  }

  function placeMenu(button, menu) {
    var box = button.getBoundingClientRect();
    var margin = 8;
    var top = Math.round(box.bottom + 4);
    menu.style.position = "fixed";
    menu.style.top = top + "px";
    menu.style.left = "auto";
    menu.style.width = "";
    menu.style.right = Math.round(window.innerWidth - box.right) + "px";
    menu.style.maxHeight = Math.max(160, window.innerHeight - top - margin) + "px";
    var width = menu.getBoundingClientRect().width;
    var right = Math.round(window.innerWidth - box.right);
    if (right + width > window.innerWidth - margin) {
      menu.style.left = margin + "px";
      menu.style.right = margin + "px";
      menu.style.width = "auto";
    }
  }

  document.querySelectorAll("[data-pref-gear]").forEach(function (button) {
    button.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      var menu = button.parentElement.querySelector(".pref-menu");
      if (!menu) {
        return;
      }
      var open = menu.classList.contains("show");
      closeMenus();
      if (!open) {
        menu.classList.add("show");
        placeMenu(button, menu);
      }
    });
  });
  document.querySelectorAll(".pref-menu").forEach(function (menu) {
    menu.addEventListener("click", function (event) {
      event.stopPropagation();
    });
  });
  document.addEventListener("click", closeMenus);
  window.addEventListener("resize", closeMenus);

  function cell(text) {
    var item = document.createElement("td");
    item.textContent = text;
    return item;
  }

  function paintPositions(data) {
    var help = document.getElementById("positions-help");
    if (help && data.positions_help) {
      help.textContent = data.positions_help;
    }
    var body = document.getElementById("positions-body");
    var table = document.getElementById("positions-table");
    var empty = document.getElementById("positions-empty");
    if (!body) {
      return;
    }
    var rows = data.positions || [];
    body.replaceChildren();
    if (!rows.length) {
      if (table) {
        table.classList.add("d-none");
      }
      if (empty) {
        empty.classList.remove("d-none");
      }
      return;
    }
    if (table) {
      table.classList.remove("d-none");
    }
    if (empty) {
      empty.classList.add("d-none");
    }
    rows.forEach(function (row) {
      var line = document.createElement("tr");
      if (row.ready) {
        line.className = "table-success";
      }
      var symbol = document.createElement("td");
      symbol.title = row.score_detail || "";
      symbol.append(document.createTextNode(row.asset || ""));
      symbol.append(document.createElement("br"));
      var bought = document.createElement("small");
      bought.textContent = row.bought || "";
      symbol.append(bought);
      if (row.score) {
        symbol.append(document.createElement("br"));
        var score = document.createElement("small");
        score.textContent = row.score;
        symbol.append(score);
      }
      var now = document.createElement("td");
      now.append(document.createTextNode(row.now || ""));
      if (row.now_time) {
        now.append(document.createElement("br"));
        var when = document.createElement("small");
        when.textContent = row.now_time;
        now.append(when);
      }
      line.append(symbol, cell(row.amount || ""), cell(row.cost || ""), now, cell(row.profit || ""), cell(row.outcome || ""));
      body.append(line);
    });
  }

  function applyAppearance(key, value) {
    var root = document.documentElement;
    if (key === "font_family") {
      root.setAttribute("data-font", value);
    }
    if (key === "ui_scale") {
      root.style.setProperty("--ui-scale", value);
      root.setAttribute("data-scale", value);
    }
    if (key === "ui_weight") {
      root.style.setProperty("--bs-body-font-weight", value);
    }
    if (key === "ui_theme") {
      root.setAttribute("data-theme", value);
      var theme = value;
      if (value === "auto") {
        var hour = new Date().getHours();
        theme = hour >= 7 && hour < 19 ? "light" : "dark";
      }
      root.setAttribute("data-bs-theme", theme);
      document.body.classList.toggle("bg-body", theme === "dark");
      document.body.classList.toggle("bg-light", theme !== "dark");
    }
    if (key === "notice_seconds") {
      document.querySelectorAll(".slide-note").forEach(function (note) {
        note.style.setProperty("--linger", value + "s");
      });
    }
  }

  document.querySelectorAll("[data-pref-step]").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = button.parentElement.querySelector("[data-pref]");
      if (!input) {
        return;
      }
      var step = Number(input.getAttribute("step"));
      var min = Number(input.getAttribute("min"));
      var max = Number(input.getAttribute("max"));
      var raw = String(input.value).trim().replace(",", ".");
      var current = Number(raw);
      if (!raw || !isFinite(current)) {
        current = Number(input.getAttribute("data-saved"));
      }
      var text = String(input.getAttribute("step"));
      var places = text.indexOf(".") >= 0 ? text.split(".")[1].length : 0;
      var scale = Math.pow(10, places);
      var next = Math.round((current + step * Number(button.getAttribute("data-dir"))) * scale) / scale;
      if (next < min) {
        next = min;
      }
      if (next > max) {
        next = max;
      }
      next = Math.round(next * scale) / scale;
      var shown = places ? next.toFixed(places) : String(next);
      if (shown === input.value) {
        return;
      }
      input.value = shown;
      input.dispatchEvent(new Event("change"));
    });
  });

  document.querySelectorAll("[data-pref]").forEach(function (input) {
    input.addEventListener("change", function () {
      var key = input.getAttribute("data-pref");
      var previous = input.getAttribute("data-saved");
      var value = String(input.value).trim().replace(",", ".");
      if (value === previous) {
        return;
      }
      var fields = {};
      fields[key] = value;
      savePref(fields).then(function (data) {
        var stored = String(data.values[key]);
        document.querySelectorAll("[data-pref='" + key + "']").forEach(function (other) {
          other.value = stored;
          other.setAttribute("data-saved", stored);
        });
        applyAppearance(key, stored);
        if (data.positions) {
          paintPositions(data);
        }
        document.dispatchEvent(new CustomEvent("prefs-applied", { detail: { key: key, value: stored } }));
      }).catch(function () {
        input.value = previous;
      });
    });
  });
})();

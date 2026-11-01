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
    var img = document.getElementById("grafico");
    if (!img || !img.getAttribute("src")) {
      return;
    }
    var url = new URL(img.getAttribute("src"), location.origin);
    if (url.searchParams.get("tema") === theme) {
      return;
    }
    url.searchParams.set("tema", theme);
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

  var openPanel = document.body.dataset.pannello;
  if (openPanel) {
    var toggle = document.getElementById(openPanel + "-toggle");
    if (toggle) {
      bootstrap.Dropdown.getOrCreateInstance(toggle).show();
    }
  }

  var volumeControls = document.getElementById("volume-controls");
  var volumeMap = document.getElementById("volume-map");
  var volumeCaption = document.getElementById("volume-caption");
  var volumeSessions = document.getElementById("volume-sessions");
  var volumeTitles = document.getElementById("volume-titles");
  var volumeSector = document.getElementById("volume-sector");
  var volumeGroup = document.getElementById("volume-group");
  var volumeCatalog = document.getElementById("volume-group-catalog");
  if (volumeControls && volumeMap && volumeSessions && volumeTitles && volumeSector && volumeGroup && volumeCatalog) {
    var volumeToken = 0;

    function clampVolume(kind, value) {
      if (kind === "sessions") {
        return Math.min(120, Math.max(1, value));
      }
      var snapped = Math.round(value / 10) * 10;
      return Math.min(500, Math.max(10, snapped));
    }

    function paintVolume(tiles) {
      volumeMap.replaceChildren();
      tiles.forEach(function (tile) {
        var node = document.createElement("div");
        node.className = "tile " + tile.kind + " " + tile.tone + " position-absolute overflow-hidden d-flex align-items-center justify-content-center text-center small lh-sm text-white border border-white";
        node.title = tile.title;
        node.style.setProperty("--x", tile.x + "%");
        node.style.setProperty("--y", tile.y + "%");
        node.style.setProperty("--w", tile.w + "%");
        node.style.setProperty("--h", tile.h + "%");
        var full = document.createElement("span");
        full.className = "full";
        full.append(document.createTextNode(tile.label), document.createElement("br"));
        var change = document.createElement("span");
        change.className = "chg text-nowrap";
        change.textContent = tile.change;
        full.append(change);
        var short = document.createElement("span");
        short.className = "short";
        short.textContent = tile.label;
        node.append(full, short);
        volumeMap.append(node);
      });
    }

    var volumeSaved = {
      sessions: volumeSessions.value,
      titles: volumeTitles.value,
      sector: volumeSector.value,
      group: volumeGroup.value
    };

    function fillGroups(sector, groupValue) {
      volumeGroup.replaceChildren();
      var all = document.createElement("option");
      all.value = "";
      all.textContent = "Tutti";
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
      volumeSector.value = volumeSaved.sector;
      fillGroups(volumeSaved.sector, volumeSaved.group);
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
      body.set("volume_class", composeClass());
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
          var prefSessions = document.getElementById("pref-return");
          var prefTitles = document.getElementById("pref-names");
          if (prefSessions) {
            prefSessions.value = volumeSessions.value;
          }
          if (prefTitles) {
            prefTitles.value = volumeTitles.value;
          }
          if (volumeCaption) {
            volumeCaption.textContent = data.caption;
          }
          paintVolume(data.tiles || []);
          setVolumeBusy(false);
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
        input.value = kind === "sessions" ? volumeSaved.sessions : volumeSaved.titles;
        return;
      }
      input.value = String(clampVolume(kind, value));
      var saved = kind === "sessions" ? volumeSaved.sessions : volumeSaved.titles;
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

    volumeControls.querySelectorAll("[data-volume-step]").forEach(function (button) {
      button.addEventListener("click", function () {
        var kind = button.getAttribute("data-volume-step");
        var input = kind === "sessions" ? volumeSessions : volumeTitles;
        var step = kind === "sessions" ? 1 : 10;
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
  }

  var frameEl = document.getElementById("grafico-frame");
  var img = document.getElementById("grafico");
  var svg = document.getElementById("grafico-svg");
  var select = document.getElementById("titolo");
  if (!img || !select || !frameEl) {
    return;
  }
  var vectorMode = frameEl.dataset.render === "vector";
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
    var url = new URL(img.dataset.chart, location.origin);
    url.searchParams.set("asset", select.value);
    url.searchParams.set("periodo", chosen("periodo"));
    url.searchParams.set("grafico", chosen("grafico"));
    url.searchParams.set("w", String(box.w));
    url.searchParams.set("h", String(box.h));
    url.searchParams.set("scala", document.documentElement.dataset.scale || "100");
    url.searchParams.set("tema", document.documentElement.getAttribute("data-bs-theme") || "light");
    url.searchParams.set("peso", getComputedStyle(document.documentElement).getPropertyValue("--bs-body-font-weight").trim() || "400");
    return url.pathname + url.search;
  }

  function remember(vista) {
    var params = new URLSearchParams(location.search);
    params.set("vista", vista);
    params.set("asset", select.value);
    params.set("periodo", chosen("periodo"));
    params.set("grafico", chosen("grafico"));
    params.delete("ok");
    params.delete("err");
    history.replaceState(null, "", location.pathname + "?" + params.toString());
  }

  var drawn = "";
  var statsBox = document.getElementById("statistiche");
  var statsKey = select.value + "|" + chosen("periodo");

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
    var key = select.value + "|" + chosen("periodo");
    if (key === statsKey) {
      return;
    }
    var url = new URL(statsBox.dataset.stats, location.origin);
    url.searchParams.set("asset", select.value);
    url.searchParams.set("periodo", chosen("periodo"));
    fetch(url.pathname + url.search, { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("stats");
        }
        return response.json();
      })
      .then(function (data) {
        if (select.value + "|" + chosen("periodo") !== key) {
          return;
        }
        statsKey = key;
        fillStats(data);
      })
      .catch(function () {});
  }

  var hitLayer = document.getElementById("grafico-hit");
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
    url.searchParams.set("periodo", chosen("periodo"));
    url.searchParams.set("grafico", chosen("grafico"));
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
    var pad = range * 0.22 || high * 0.012 || 1;
    low -= pad;
    high += pad;
    var sample = priceText(high);
    var left = Math.ceil(10 + sample.length * tick * 0.62);
    var right = width - 12;
    var top = tick + 22;
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

    var title = svgEl("text", {
      x: left,
      y: tick + 4,
      fill: "var(--bs-body-color)",
      "font-size": (tick + 2) + "px",
      "font-weight": String(titleWeight)
    });
    title.textContent = data.title;
    svg.appendChild(title);

    axisTicks(low, high).forEach(function (value) {
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
    url.searchParams.set("periodo", chosen("periodo"));
    url.searchParams.set("grafico", chosen("grafico"));
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
    if (vectorMode) {
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
    remember("storico");
    loadStats();
  }

  select.addEventListener("change", paint);

  document.querySelectorAll("[data-periodo], [data-grafico]").forEach(function (button) {
    button.addEventListener("click", function () {
      var name = button.hasAttribute("data-periodo") ? "periodo" : "grafico";
      document.querySelectorAll("[data-" + name + "]").forEach(function (other) {
        other.classList.remove("active");
      });
      button.classList.add("active");
      paint();
    });
  });

  var volumeTab = document.getElementById("volume-tab");
  var storicoTab = document.getElementById("storico-tab");
  if (volumeTab) {
    volumeTab.addEventListener("shown.bs.tab", function () {
      remember("volume");
    });
  }
  if (storicoTab) {
    storicoTab.addEventListener("shown.bs.tab", function () {
      paint();
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
  var modal = document.getElementById("preferenze");
  var form = modal ? modal.querySelector("form") : null;
  var wait = document.getElementById("pref-wait");
  if (!modal || !form) {
    return;
  }
  var sending = false;

  function showWait() {
    if (!wait) {
      return;
    }
    wait.classList.remove("d-none");
    wait.classList.add("d-flex");
  }

  form.addEventListener("submit", function (event) {
    if (sending) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    sending = true;
    var button = form.querySelector("[type=submit]");
    if (button) {
      button.disabled = true;
    }
    var gone = false;
    function leave() {
      if (gone) {
        return;
      }
      gone = true;
      showWait();
      form.submit();
    }
    modal.addEventListener("hidden.bs.modal", leave, { once: true });
    window.setTimeout(leave, 400);
    bootstrap.Modal.getOrCreateInstance(modal).hide();
  });
})();

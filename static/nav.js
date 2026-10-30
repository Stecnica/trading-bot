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
      body.set("universe_size", volumeTitles.value);
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
          var prefTitles = document.getElementById("pref-universe");
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

  var img = document.getElementById("grafico");
  var select = document.getElementById("titolo");
  if (!img || !select) {
    return;
  }

  function chosen(name) {
    var button = document.querySelector("[data-" + name + "].active");
    return button ? button.getAttribute("data-" + name) : "";
  }

  function frame() {
    var width = img.clientWidth;
    if (width < 200 && img.parentElement) {
      width = img.parentElement.clientWidth;
    }
    width = Math.round(width);
    var top = img.getBoundingClientRect().top;
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
  note.className = "position-absolute z-3 d-none pe-none bg-white text-dark border rounded-2 px-2 py-1 shadow";
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
    var box = hitLayer.getBoundingClientRect();
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

  function paint() {
    var box = frame();
    if (box.w < 200) {
      return;
    }
    var next = chartUrl(box);
    if (next !== drawn) {
      drawn = next;
      img.src = next;
    }
    img.alt = "Andamento e volumi di " + select.value;
    remember("storico");
    loadStats();
    paintHits();
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

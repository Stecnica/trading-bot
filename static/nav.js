(function () {
  function place(button) {
    var menu = button.nextElementSibling;
    if (!menu) {
      return;
    }
    var drop = button.parentElement.getBoundingClientRect();
    var note = document.querySelector(".slide-note");
    var target = note ? note.getBoundingClientRect().bottom + 8 : drop.bottom + 2;
    menu.style.marginTop = Math.max(2, Math.round(target - drop.bottom)) + "px";
    menu.style.transform = "";
    if (!menu.classList.contains("nav-panel")) {
      return;
    }
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
    img.alt = "Andamento di " + select.value;
    remember("storico");
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

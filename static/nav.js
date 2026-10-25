(function () {
  var img = document.getElementById("grafico");
  var select = document.getElementById("titolo");
  if (!img || !select) {
    return;
  }

  function chosen(name) {
    var button = document.querySelector("[data-" + name + "].active");
    return button ? button.getAttribute("data-" + name) : "";
  }

  function chartUrl() {
    var url = new URL(img.dataset.chart, location.origin);
    url.searchParams.set("asset", select.value);
    url.searchParams.set("periodo", chosen("periodo"));
    url.searchParams.set("grafico", chosen("grafico"));
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

  function paint() {
    var next = chartUrl();
    if (!img.src.endsWith(next)) {
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
})();

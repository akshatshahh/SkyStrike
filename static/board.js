(function () {
  var chips = document.querySelectorAll("[data-filter]");
  var rows = document.querySelectorAll(".board .row");
  if (!chips.length) return;

  var current = "all";

  function apply() {
    rows.forEach(function (row) {
      var days = Number(row.getAttribute("data-days"));
      var priced = row.getAttribute("data-priced") === "1";
      var city = row.getAttribute("data-city") || "";
      var show = true;
      if (current === "priced") show = priced;
      else if (current === "week") show = !isNaN(days) && days >= 0 && days <= 7;
      else if (current.indexOf("city:") === 0) show = city === current.slice(5);
      row.hidden = !show;
    });
    chips.forEach(function (chip) {
      chip.classList.toggle("on", chip.getAttribute("data-filter") === current);
    });
  }

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      current = chip.getAttribute("data-filter") || "all";
      apply();
    });
  });
})();

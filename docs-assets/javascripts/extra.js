// Reading progress bar
document$.subscribe(function () {
  var bar = document.createElement("div");
  bar.id = "reading-progress";
  bar.style.cssText =
    "position:fixed;top:0;left:0;height:3px;z-index:1000;" +
    "background:linear-gradient(90deg,#ff8f00,#c62828);transition:width .15s";
  document.body.appendChild(bar);

  function update() {
    var scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
    var scrollHeight =
      document.documentElement.scrollHeight -
      document.documentElement.clientHeight;
    bar.style.width = (scrollTop / scrollHeight) * 100 + "%";
  }

  window.addEventListener("scroll", update);
  update();
});

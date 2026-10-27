(function () {
	var note = document.querySelector("[data-anteprima]");
	if (!note) {
		return;
	}
	var states = [
		["message", "Messaggio<br>Testo primary, bordo primary<br>Fondo info più trasparente", "text-primary bg-info border-primary opacity-50"],
		["success", "Successo<br>Testo, bordo e fondo success<br>Opacità sull'intero blocco", "text-success bg-success-subtle border-success"],
		["warning", "Avviso<br>Testo danger<br>Bordo e fondo warning", "text-danger bg-warning-subtle border-warning"],
		["alert", "Allarme<br>Testo, bordo e fondo danger<br>Opacità sull'intero blocco", "text-danger bg-danger-subtle border-danger"]
	];
	var index = 0;
	function show() {
		var state = states[index];
		note.className = "slide-note anteprima border rounded-4 text-center pe-none px-3 py-2 " + state[2];
		note.innerHTML = state[1];
		index = (index + 1) % states.length;
	}
	show();
	window.setInterval(show, 4000);
})();

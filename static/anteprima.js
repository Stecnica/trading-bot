(function () {
	var note = document.querySelector("[data-anteprima]");
	if (!note) {
		return;
	}
	var bag = {};
	var node = document.getElementById("i18n");
	try {
		bag = node ? JSON.parse(node.textContent) : {};
	} catch (error) {
		bag = {};
	}
	var states = [
		["message", bag["preview.message"] || "", "text-primary bg-info border-primary opacity-50"],
		["success", bag["preview.success"] || "", "text-success bg-success-subtle border-success"],
		["warning", bag["preview.warning"] || "", "text-danger bg-warning-subtle border-warning"],
		["alert", bag["preview.alert"] || "", "text-danger bg-danger-subtle border-danger"]
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

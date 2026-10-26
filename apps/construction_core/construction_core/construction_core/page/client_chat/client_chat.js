// Client Chat (P1-14, D-098), retired by P3-74 (FIT-10, D-419): the staff Discussion inbox in the workspace replaces it.
// The page keeps its Desk route, so old links and the project form's "Client chat" button land on the inbox; an old link
// to one conversation (?thread=) goes through the thread's Desk form, which opens it in its room in the workspace.

frappe.pages["client-chat"].on_page_load = function () {
	const thread = new URLSearchParams(window.location.search).get("thread");
	if (thread) {
		window.location.replace(`/app/discuss-thread/${encodeURIComponent(thread)}`);
		return;
	}
	window.location.replace("/workspace/discussion");
};

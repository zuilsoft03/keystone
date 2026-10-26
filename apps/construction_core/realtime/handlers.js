// P3-13 (R-13; D-200, D-203): a socket of a turned-off account, or of a session that has ended, is closed.
// Frappe's realtime server checks a socket's session once, when it connects (realtime/middlewares/authenticate.js),
// and loads this file for every installed app (realtime/index.js, get_app_handlers).
// - At once: a turn-off is announced on the Redis channel `cc_session_end` ({namespace, user}) after its commit
//   (construction_core.accounts.sessions.announce_end); every socket of that account in that site is closed.
// - Backstop: every 60 s each signed-in socket asks the site who it is; the site's auth hook answers 401 for a
//   turned-off account, and an ended session answers as Guest. Network trouble and server errors never close a socket.

const INTERVAL_MS = 60 * 1000;
const CHECK_TIMEOUT_MS = 15 * 1000;
const CHANNEL = "cc_session_end";
const sockets = new Map(); // "<namespace>|<user>" -> Set of sockets
let subscriber = null;

function key_of(namespace, user) {
	return `${namespace}|${user}`;
}

async function still_signed_in(socket) {
	let res;
	try {
		res = await socket.frappe_request("/api/method/frappe.realtime.get_user_info", {}, {
			signal: AbortSignal.timeout(CHECK_TIMEOUT_MS), // a slow site never piles checks up
		});
	} catch (e) {
		return true;
	}
	if (res.status === 401 || res.status === 403) return false;
	if (!res.ok) return true;
	let message;
	try {
		({ message } = await res.json());
	} catch (e) {
		return true;
	}
	if (!message || !message.user) return true; // no socket secret answer: not a refusal
	return message.user === socket.user;
}

function on_end(raw) {
	let m;
	try {
		m = JSON.parse(raw);
	} catch (e) {
		return 0;
	}
	if (!m || !m.namespace || !m.user) return 0;
	const set = sockets.get(key_of(`/${m.namespace}`, m.user));
	if (!set) return 0;
	const closing = [...set];
	closing.forEach((s) => s.disconnect(true));
	return closing.length;
}

function listen() {
	if (subscriber || process.env.CC_REALTIME_NO_SUBSCRIBE) return;
	try {
		const { get_redis_subscriber } = require("../../frappe/node_utils");
		subscriber = get_redis_subscriber();
		subscriber
			.connect()
			.then(() => subscriber.subscribe(CHANNEL, on_end))
			.catch((err) => console.warn(`construction_core: cannot listen on ${CHANNEL}`, err));
	} catch (err) {
		console.warn(`construction_core: cannot listen on ${CHANNEL}`, err);
	}
}

function construction_handlers(socket) {
	if (!socket.user || socket.user === "Guest") return;
	listen();
	const key = key_of(socket.nsp.name, socket.user);
	if (!sockets.has(key)) sockets.set(key, new Set());
	sockets.get(key).add(socket);
	const timer = setInterval(async () => {
		if (!(await still_signed_in(socket))) socket.disconnect(true);
	}, INTERVAL_MS);
	socket.on("disconnect", () => {
		clearInterval(timer);
		const set = sockets.get(key);
		if (set) {
			set.delete(socket);
			if (!set.size) sockets.delete(key);
		}
	});
}

module.exports = construction_handlers;
module.exports.still_signed_in = still_signed_in;
module.exports.on_end = on_end;

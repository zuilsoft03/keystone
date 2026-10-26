// Live updates (ARCHITECTURE §4, DR-8): one socket to this site's namespace on the same origin. The realtime server
// joins it to the user's own room on connect, so per-user events need no subscribe call.
import { io } from 'socket.io-client'
import { boot } from './boot.js'

let socket = null

function getSocket() {
  if (!socket) {
    socket = io(`${window.location.origin}/${boot.sitename}`, { withCredentials: true, reconnectionAttempts: 10 })
  }
  return socket
}

// Returns the function that removes the handler; every caller removes its handlers on unmount.
export function onEvent(event, handler) {
  const s = getSocket()
  s.on(event, handler)
  return () => s.off(event, handler)
}

// A document room (staff only: the server refuses a client's doc_subscribe, D-100). Returns the unsubscribe.
export function subscribeDoc(doctype, name) {
  const s = getSocket()
  const join = () => s.emit('doc_subscribe', doctype, name)
  join()
  s.on('connect', join) // rejoin after a reconnect
  return () => {
    s.off('connect', join)
    s.emit('doc_unsubscribe', doctype, name)
  }
}

export function isConnected() {
  return Boolean(socket && socket.connected)
}

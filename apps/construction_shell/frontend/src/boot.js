// What the page put in before the app loaded (workspace_page.boot). Not a permission: the server checks every call.
export const boot = Object.freeze(window.cc_boot || {})

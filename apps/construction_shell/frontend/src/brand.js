// P3-45 (D-300; docs/design/brand.md): a firm's brand reaches the screens as CSS custom properties, never as CSS text. A
// colour passes only as a six-digit hex, the font only as a key of the fixed map below, and an image only as a path on
// this site; anything else is dropped, so a boot string cannot inject a rule. The server checks the same things; this is
// the second line, and the Brand page's live preview uses the very same guard.
export const HEX = /^#[0-9a-f]{6}$/i

// The four heading faces the Brand page offers (self-hosted, src/assets/fonts). The key is what the server stores.
export const FONTS = {
  archivo: { name: 'Archivo', family: "'Archivo'" },
  'barlow-semi-condensed': { name: 'Barlow Semi Condensed', family: "'Barlow Semi Condensed'" },
  manrope: { name: 'Manrope', family: "'Manrope'" },
  'ibm-plex-sans': { name: 'IBM Plex Sans', family: "'IBM Plex Sans'" },
}

export const hexOf = (value) => (typeof value === 'string' && HEX.test(value) ? value.toLowerCase() : '')
export const familyOf = (key) => (typeof key === 'string' && Object.hasOwn(FONTS, key) ? FONTS[key].family : '')
// A path on this site (no scheme, no host, no quote or bracket that could end a URL early).
export const pathOf = (value) => (typeof value === 'string' && /^\/(?!\/)[\w\-./%?=&~]*$/.test(value) ? value : '')

/** What a page may use of a brand (the boot's or the draft's): every field checked, "" when missing or not valid. */
export function looksOf(brand) {
  const b = brand && typeof brand === 'object' ? brand : {}
  return {
    main: hexOf(b.main), hover: hexOf(b.main_hover), press: hexOf(b.main_press), panel: hexOf(b.panel),
    family: familyOf(b.heading_font), logo: pathOf(b.logo_url), picture: pathOf(b.signin_picture),
  }
}

/** The custom properties a look sets (only those with a valid value); style.css maps them onto the design system's tokens. */
export function varsOf(look) {
  const vars = {}
  if (look.main) {
    vars['--brand-main'] = look.main
    // the server derives hover and press; a draft that has none keeps the main colour
    vars['--brand-main-hover'] = look.hover || look.main
    vars['--brand-main-press'] = look.press || look.main
  }
  if (look.panel) vars['--brand-panel'] = look.panel
  if (look.family) vars['--brand-heading'] = look.family
  return vars
}

/** Sets the look on an element: the page's root, or the Brand page's preview. Clears what it set before. */
export function applyLook(look, root = document.documentElement) {
  for (const name of ['--brand-main', '--brand-main-hover', '--brand-main-press', '--brand-panel', '--brand-heading']) root.style.removeProperty(name)
  const vars = varsOf(look)
  for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value)
  if (vars['--brand-main']) root.setAttribute('data-brand-main', '')
  else root.removeAttribute('data-brand-main')
}


/** The look a page's boot carries (the screens read it through this, not the boot's field). */
export const bootLook = (boot) => looksOf(boot && boot.brand)

// The Brand page's fields: the form key, the server's saved key and the call's argument.
export const FIELDS = [
  ['company_name', 'company', 'company_name'],
  ['main_colour', 'main', 'main_colour'],
  ['panel_colour', 'panel', 'panel_colour'],
  ['heading_font', 'heading_font', 'heading_font'],
]

/** The form's values from what the server holds. */
export const formOf = (brand) => Object.fromEntries(FIELDS.map(([key, saved]) => [key, (brand && brand[saved]) || '']))

/** The one call's arguments: only the fields that differ from what the server holds (it updates only what it is given, D-344). */
export function changedFields(form, brand) {
  const saved = formOf(brand)
  return Object.fromEntries(FIELDS.filter(([key]) => (form[key] || '').trim() !== saved[key]).map(([key]) => [key, form[key].trim()]))
}

/** The brand dict a draft stands for, for the live preview: the same guard as the boot's. */
export const draftOf = (form, brand) => ({ ...brand, company: form.company_name.trim(), main: form.main_colour.trim(), main_hover: '', main_press: '', panel: form.panel_colour.trim(), heading_font: form.heading_font })

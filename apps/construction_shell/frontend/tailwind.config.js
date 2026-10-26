// frappe-ui 1.0's Tailwind preset is the whole palette: its semantic surface, ink and outline tokens, with dark values
// under [data-theme="dark"] (D-125, D-126). The shell adds no colours of its own; the guard in tests/theme.test.js keeps
// it that way. Its sources are in `content` because Tailwind 3 does not merge `content` from a preset.
import frappeUiPreset, { content as frappeUiContent } from 'frappe-ui/tailwind'

export default {
  presets: [frappeUiPreset],
  content: [...frappeUiContent, './src/**/*.{vue,js}'],
}

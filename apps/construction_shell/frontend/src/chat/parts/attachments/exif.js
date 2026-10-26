// A photo's capture time, read in the browser before its own shrink drops the EXIF (P3-65, design §3.3, L-16): the
// camera's DateTimeOriginal (else DateTime) of a JPEG, as the camera's wall time "YYYY-MM-DD HH:MM:SS". Nothing else
// is read, the place never. The server prefers the file's own EXIF time; this is used only when the shrunk copy has
// none. A file that is not a JPEG, or has no readable time, answers ''.
const HEAD = 256 * 1024 // EXIF sits in the first segments

export async function captureTime(file) {
  if (!file || !(/jpe?g$/i.test(file.type || '') || /\.jpe?g$/i.test(file.name || ''))) return ''
  try {
    return exifTime(new DataView(await file.slice(0, HEAD).arrayBuffer()))
  } catch {
    return ''
  }
}

export function exifTime(view) {
  try {
    if (view.byteLength < 4 || view.getUint16(0) !== 0xFFD8) return ''
    let at = 2
    while (at + 10 <= view.byteLength) {
      const marker = view.getUint16(at)
      if ((marker & 0xFF00) !== 0xFF00 || marker === 0xFFDA) return '' // not a segment, or the image data starts
      if (marker === 0xFFE1 && view.getUint32(at + 4) === 0x45786966) return fromTiff(view, at + 10) // "Exif"
      at += 2 + view.getUint16(at + 2)
    }
  } catch { /* a cut or broken header */ }
  return ''
}

function fromTiff(view, start) {
  const little = view.getUint16(start) === 0x4949
  const u16 = (o) => view.getUint16(start + o, little)
  const u32 = (o) => view.getUint32(start + o, little)
  const entry = (ifd, tag) => {
    const n = u16(ifd)
    for (let i = 0; i < n && i < 512; i++) if (u16(ifd + 2 + i * 12) === tag) return ifd + 2 + i * 12
    return -1
  }
  const text = (e) => {
    const count = u32(e + 4)
    const offset = count > 4 ? u32(e + 8) : e + 8
    let s = ''
    for (let i = 0; i < Math.min(count, 19); i++) s += String.fromCharCode(view.getUint8(start + offset + i))
    return s
  }
  const ifd0 = u32(4)
  const pointer = entry(ifd0, 0x8769) // the Exif IFD
  let e = pointer >= 0 ? entry(u32(pointer + 8), 0x9003) : -1 // DateTimeOriginal
  if (e < 0) e = entry(ifd0, 0x0132) // DateTime
  if (e < 0) return ''
  const m = /^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/.exec(text(e))
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}` : ''
}

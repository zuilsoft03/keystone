// The browser's shrink of a photo picked on a phone (P3-65, design §3.3, L-11): at most SHRINK_PX on the long edge,
// turned upright, in its own type. "Send original quality" skips it, for renders and drawings. An image the browser
// cannot draw goes as it is: the server checks and rebuilds every image anyway.
export const SHRINK_PX = 2048
const TYPES = ['image/jpeg', 'image/png', 'image/webp']

export async function shrinkImage(file, max = SHRINK_PX) {
  if (!file || !TYPES.includes(file.type) || typeof createImageBitmap !== 'function') return file
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' }).catch(() => null)
  if (!bitmap) return file
  try {
    const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height))
    if (scale >= 1) return file
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, file.type, 0.9))
    // A browser that cannot encode the type (WebP in some Safari versions) hands back a PNG: the original goes instead
    return blob && blob.type === file.type ? new File([blob], file.name, { type: file.type, lastModified: file.lastModified }) : file
  } finally {
    bitmap.close?.()
  }
}

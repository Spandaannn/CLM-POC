/** Client-side checks that mirror the server's upload rules. */
export const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024

const ALLOWED_EXTENSIONS = ['.pdf', '.docx']

/** Return an error message, or null if the file looks acceptable. */
export function validateDocumentFile(file: File): string | null {
  const name = file.name.toLowerCase()

  if (!ALLOWED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return 'Only PDF (.pdf) and Word (.docx) files can be uploaded.'
  }
  if (file.size === 0) {
    return 'This file is empty. Choose a different file.'
  }
  if (file.size > MAX_DOCUMENT_BYTES) {
    return 'This file is larger than the 10 MB limit.'
  }
  return null
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

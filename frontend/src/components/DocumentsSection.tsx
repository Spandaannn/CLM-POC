import { useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { downloadDocument, uploadDocument } from '../api/documents'
import type { ContractDocument } from '../api/types'
import { formatFileSize, validateDocumentFile } from '../lib/documentFile'
import { getErrorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import type { DocumentsLoadState } from '../lib/useDocuments'
import { Alert } from './Alert'
import { Button } from './Button'
import { Spinner } from './Spinner'

interface DocumentsSectionProps {
  contractId: string
  /** Shared with the AI Reviews section, which needs the current version. */
  documents: { state: DocumentsLoadState; reload: () => void }
  /** The creator or an administrator may upload new versions. */
  canUpload: boolean
  /** Why uploads are paused (approval workflow), or null if they are open. */
  lockedReason?: string | null
}

const FILE_ACCEPT =
  '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

/** Documents panel for the contract detail page: upload, versions, download. */
export function DocumentsSection({
  contractId,
  documents,
  canUpload,
  lockedReason = null,
}: DocumentsSectionProps) {
  const { state, reload } = documents
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  const latestVersion =
    state.status === 'loaded' ? (state.data.current?.version_number ?? 0) : 0

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null
    setUploadError(null)
    setUploadSuccess(null)

    if (!selected) {
      setFile(null)
      setFileError(null)
      return
    }

    const problem = validateDocumentFile(selected)
    setFileError(problem)
    setFile(problem ? null : selected)

    // Clear an invalid selection so the same file can be re-chosen later.
    if (problem && fileInputRef.current) fileInputRef.current.value = ''
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!file || isUploading) return

    setIsUploading(true)
    setUploadError(null)
    setUploadSuccess(null)
    setDownloadError(null)

    try {
      const created = await uploadDocument(contractId, file)
      setUploadSuccess(
        `${created.original_filename} uploaded as version ${created.version_number}.`,
      )
      setFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      reload()
    } catch (caughtError) {
      setUploadError(getErrorMessage(caughtError))
    } finally {
      setIsUploading(false)
    }
  }

  async function handleDownload(document: ContractDocument) {
    setDownloadingId(document.id)
    setDownloadError(null)
    setUploadError(null)
    setUploadSuccess(null)

    try {
      await downloadDocument(document)
    } catch (caughtError) {
      setDownloadError(getErrorMessage(caughtError))
    } finally {
      setDownloadingId(null)
    }
  }

  return (
    <section className="detail-card documents" aria-labelledby="documents-title">
      <div className="documents__header">
        <div>
          <h2 id="documents-title">Documents</h2>
          <p className="muted-text">
            PDF or Word (.docx), up to 10 MB. Each upload is saved as a new
            version; earlier versions are kept.
          </p>
        </div>
      </div>

      {canUpload && lockedReason ? (
        <p className="approval__lock" role="status">
          {lockedReason}
        </p>
      ) : canUpload ? (
        <form className="upload-form" onSubmit={handleUpload} noValidate>
          <div className="field">
            <label className="field__label" htmlFor="document-file">
              {latestVersion > 0
                ? `Upload version ${latestVersion + 1}`
                : 'Upload a document'}
            </label>
            <input
              ref={fileInputRef}
              id="document-file"
              className={`field__input${fileError ? ' field__input--error' : ''}`}
              type="file"
              accept={FILE_ACCEPT}
              onChange={handleFileChange}
              disabled={isUploading}
              aria-invalid={fileError ? true : undefined}
              aria-describedby={fileError ? 'document-file-error' : undefined}
            />
            {fileError && (
              <p className="field__error" id="document-file-error" role="alert">
                {fileError}
              </p>
            )}
          </div>
          <Button type="submit" loading={isUploading} disabled={!file}>
            {isUploading ? 'Uploading...' : 'Upload'}
          </Button>
        </form>
      ) : (
        <p className="muted-text">
          Only the contract creator or an administrator can upload new
          versions.
        </p>
      )}

      {uploadError && <Alert variant="error">{uploadError}</Alert>}
      {uploadSuccess && <Alert variant="success">{uploadSuccess}</Alert>}
      {downloadError && <Alert variant="error">{downloadError}</Alert>}

      {state.status === 'loading' && (
        <div className="state-panel" role="status">
          <Spinner size={26} label="Loading documents" />
          <p>Loading documents...</p>
        </div>
      )}

      {state.status === 'error' && (
        <div className="page-error">
          <Alert variant="error">{state.message}</Alert>
          <Button variant="secondary" onClick={reload}>
            Try again
          </Button>
        </div>
      )}

      {state.status === 'loaded' && state.data.items.length === 0 && (
        <div className="empty-state documents__empty">
          <h3>No documents yet</h3>
          <p>
            {canUpload
              ? 'Upload the agreement above to start its version history.'
              : 'No document has been uploaded for this contract yet.'}
          </p>
        </div>
      )}

      {state.status === 'loaded' && state.data.items.length > 0 && (
        <>
          <h3 className="documents__subheading">
            Version history ({state.data.total})
          </h3>
          <div className="table-wrap">
            <table className="data-table">
              <caption className="visually-hidden">
                Versions of this contract&apos;s document, newest first
              </caption>
              <thead>
                <tr>
                  <th scope="col">Version</th>
                  <th scope="col">File</th>
                  <th scope="col">Size</th>
                  <th scope="col">Uploaded</th>
                  <th scope="col">Uploaded by</th>
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {state.data.items.map((document) => (
                  <tr key={document.id}>
                    <td>
                      <span className="documents__version">
                        v{document.version_number}
                      </span>{' '}
                      <span
                        className={`badge ${
                          document.is_current ? 'badge--success' : 'badge--muted'
                        }`}
                      >
                        {document.is_current ? 'Current' : 'Older'}
                      </span>
                    </td>
                    <td className="documents__filename">
                      {document.original_filename}
                    </td>
                    <td>{formatFileSize(document.file_size)}</td>
                    <td>{formatDateTime(document.uploaded_at)}</td>
                    <td>{document.uploaded_by_name ?? 'Unknown user'}</td>
                    <td>
                      <Button
                        variant="secondary"
                        onClick={() => handleDownload(document)}
                        loading={downloadingId === document.id}
                        disabled={downloadingId !== null}
                        aria-label={`Download version ${document.version_number}: ${document.original_filename}`}
                      >
                        Download
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}

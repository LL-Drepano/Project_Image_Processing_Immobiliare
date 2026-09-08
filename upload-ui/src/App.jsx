import { useState } from 'react'
import './App.css'

const CLOUD_NAME = 'fmlegosh'
const UPLOAD_PRESET = 'upload_ui'

const N8N_WEBHOOK_URL =
  'http://localhost:5678/webhook-test/photo_quality'

const N8N_CONFIRM_L4_URL =
  'http://localhost:5678/webhook-test/confirm_l4'

function App() {
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [isDragging, setIsDragging] = useState(false)

  const [isUploading, setIsUploading] = useState(false)
  const [isSubmittingConfirmation, setIsSubmittingConfirmation] =
    useState(false)

  const [uploadResult, setUploadResult] = useState(null)
  const [analysisResult, setAnalysisResult] = useState(null)
  const [confirmationResult, setConfirmationResult] = useState(null)
  const [error, setError] = useState(null)

  function resetOutcomeState() {
    setUploadResult(null)
    setAnalysisResult(null)
    setConfirmationResult(null)
    setError(null)
  }

  function setSelectedFile(selectedFile) {
    if (!selectedFile) return

    if (!selectedFile.type.startsWith('image/')) {
      setError('Seleziona un file immagine.')
      return
    }

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
    }

    setFile(selectedFile)
    setPreviewUrl(URL.createObjectURL(selectedFile))
    resetOutcomeState()
  }

  function handleFileChange(event) {
    setSelectedFile(event.target.files?.[0])
  }

  function handleDragOver(event) {
    event.preventDefault()
    setIsDragging(true)
  }

  function handleDragLeave(event) {
    event.preventDefault()
    setIsDragging(false)
  }

  function handleDrop(event) {
    event.preventDefault()
    setIsDragging(false)

    const droppedFile = event.dataTransfer.files?.[0]
    setSelectedFile(droppedFile)
  }

  function clearFile(event) {
    event.preventDefault()
    event.stopPropagation()

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
    }

    setFile(null)
    setPreviewUrl(null)
    resetOutcomeState()
  }

  async function handleAnalyze() {
    if (!file || isUploading) return

    setIsUploading(true)
    resetOutcomeState()

    try {
      // 1. Upload Cloudinary
      const formData = new FormData()

      formData.append('file', file)
      formData.append('upload_preset', UPLOAD_PRESET)

      const cloudinaryResponse = await fetch(
        `https://api.cloudinary.com/v1_1/${CLOUD_NAME}/image/upload`,
        {
          method: 'POST',
          body: formData,
        }
      )

      const cloudinaryData = await cloudinaryResponse.json()

      if (!cloudinaryResponse.ok) {
        throw new Error(
          cloudinaryData?.error?.message ||
            'Errore durante il caricamento della foto'
        )
      }

      setUploadResult({
        secureUrl: cloudinaryData.secure_url,
        publicId: cloudinaryData.public_id,
      })

      console.log('Cloudinary upload completato:', cloudinaryData)

      // 2. Chiamata webhook n8n
      const photoId = `ui_${crypto.randomUUID()}`

      const n8nResponse = await fetch(N8N_WEBHOOK_URL, {
        method: 'POST',

        headers: {
          'Content-Type': 'application/json',
        },

        body: JSON.stringify({
          photo_id: photoId,
          nome_file: file.name,
          url_input: cloudinaryData.secure_url,
          id_cloudinary_input: cloudinaryData.public_id,
        }),
      })

      const rawResponse = await n8nResponse.text()

      console.log('Risposta grezza n8n:', rawResponse)

      let result

      try {
        result = JSON.parse(rawResponse)
      } catch {
        throw new Error(
          `Risposta n8n non JSON: ${rawResponse || '(risposta vuota)'}`
        )
      }

      if (!n8nResponse.ok) {
        throw new Error(
          result?.message || 'Errore durante l’analisi della foto'
        )
      }

      console.log('Risultato pipeline:', result)

      setAnalysisResult(result)
    } catch (err) {
      console.error(err)

      setError(
        err?.message ||
          'Si è verificato un errore durante l’analisi'
      )
    } finally {
      setIsUploading(false)
    }
  }

  async function handleL4Decision(esito) {
    if (
      !analysisResult?.decision_id ||
      isSubmittingConfirmation
    ) {
      return
    }

    setIsSubmittingConfirmation(true)
    setError(null)

    try {
      const response = await fetch(N8N_CONFIRM_L4_URL, {
        method: 'POST',

        headers: {
          'Content-Type': 'application/json',
        },

        body: JSON.stringify({
          decision_id: analysisResult.decision_id,
          esito,
        }),
      })

      const rawResponse = await response.text()

      console.log('Risposta conferma L4:', rawResponse)

      let result

      try {
        result = JSON.parse(rawResponse)
      } catch {
        throw new Error(
          `Risposta conferma non JSON: ${
            rawResponse || '(risposta vuota)'
          }`
        )
      }

      if (!response.ok) {
        throw new Error(
          result?.message ||
            'Errore durante la conferma del risultato'
        )
      }

      setConfirmationResult(result)

      setAnalysisResult((prev) => {
        if (!prev) return prev

        return {
          ...prev,
          status:
            result.stato_finale === 'completed'
              ? 'completed'
              : 'rejected',
        }
      })
    } catch (err) {
      console.error(err)

      setError(
        err?.message ||
          'Si è verificato un errore durante la conferma'
      )
    } finally {
      setIsSubmittingConfirmation(false)
    }
  }

  function renderResult() {
    if (!analysisResult) return null

    const originalImageUrl =
      uploadResult?.secureUrl || previewUrl

    const outputImageUrl =
      analysisResult.output_url

    // KEEP
    if (analysisResult.route === 'KEEP') {
      return (
        <section className="result-card">
          <div className="result-header">
            <p className="result-kicker">
              Esito
            </p>

            <h2>
              La foto è già pronta
            </h2>

            <p className="result-text">
              La foto può essere usata così com’è.
              Non sono necessari interventi.
            </p>
          </div>

          {originalImageUrl && (
            <img
              src={originalImageUrl}
              alt="Foto caricata"
              className="result-single-image"
            />
          )}
        </section>
      )
    }

    // L1
    if (analysisResult.route === 'L1') {
      return (
        <section className="result-card">
          <div className="result-header">
            <p className="result-kicker">
              Esito
            </p>

            <h2>
              Foto migliorata automaticamente
            </h2>

            <p className="result-text">
              Abbiamo corretto luce e colore mantenendo
              invariato il contenuto dell’immagine.
            </p>
          </div>

          <div className="comparison-grid">
            <div className="comparison-item">
              <p className="comparison-label">
                Prima
              </p>

              <img
                src={originalImageUrl}
                alt="Foto originale"
                className="comparison-image"
              />
            </div>

            <div className="comparison-item">
              <p className="comparison-label">
                Dopo
              </p>

              <img
                src={outputImageUrl}
                alt="Foto migliorata"
                className="comparison-image"
              />
            </div>
          </div>
        </section>
      )
    }

    // RETAKE
    if (analysisResult.route === 'RETAKE') {
      return (
        <section className="result-card">
          <div className="result-header">
            <p className="result-kicker">
              Esito
            </p>

            <h2>
              Ti consigliamo di scattare nuovamente la foto
            </h2>

            <p className="result-text">
              Questa immagine non può essere migliorata in modo
              affidabile senza rischiare di inventare o alterare
              dettagli dell’immobile.
            </p>
          </div>

          {originalImageUrl && (
            <img
              src={originalImageUrl}
              alt="Foto da rifare"
              className="result-single-image"
            />
          )}
        </section>
      )
    }

    // L4
    if (analysisResult.route === 'L4') {
      const confirmed =
        confirmationResult?.esito === 'confirmed'

      const rejected =
        confirmationResult?.esito === 'rejected'

      const pending =
        analysisResult.status ===
          'pending_human_confirmation' &&
        !confirmationResult

      return (
        <section className="result-card">
          <div className="result-header">
            <p className="result-kicker">
              Verifica richiesta
            </p>

            <h2>
              Controlla che la foto rispecchi l’immobile
            </h2>

            <p className="result-text">
              Per migliorare una foto molto compromessa abbiamo
              utilizzato un intervento più avanzato. Confronta
              attentamente il risultato con l’originale e verifica
              che elementi, materiali, colori e dettagli
              dell’immobile non siano stati modificati e che la
              foto rappresenti fedelmente la realtà.
            </p>
          </div>

          <div className="comparison-grid">
            <div className="comparison-item">
              <p className="comparison-label">
                Prima
              </p>

              <img
                src={originalImageUrl}
                alt="Foto originale"
                className="comparison-image"
              />
            </div>

            <div className="comparison-item">
              <p className="comparison-label">
                Dopo
              </p>

              <img
                src={outputImageUrl}
                alt="Foto migliorata"
                className="comparison-image"
              />
            </div>
          </div>

          {pending && (
            <div className="confirmation-actions">
              <button
                type="button"
                className="primary-button"
                onClick={() =>
                  handleL4Decision('confirmed')
                }
                disabled={isSubmittingConfirmation}
              >
                {isSubmittingConfirmation
                  ? 'Invio in corso...'
                  : 'Conferma: rispecchia l’immobile'}
              </button>

              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  handleL4Decision('rejected')
                }
                disabled={isSubmittingConfirmation}
              >
                Rifiuta: non rispecchia l’immobile
              </button>
            </div>
          )}

          {confirmed && (
            <p className="upload-success">
              Risultato confermato. La foto è stata
              approvata.
            </p>
          )}

          {rejected && (
            <p className="upload-error">
              Risultato rifiutato. La versione migliorata
              non verrà considerata approvata.
            </p>
          )}
        </section>
      )
    }

    return null
  }

  return (
    <main className="page">
      <section className="card">
        <div className="header">
          <p className="eyebrow">
            Qualità foto annuncio
          </p>

          <h1>
            Migliora la foto del tuo immobile
          </h1>

          <p className="subtitle">
            Carica una foto. Verificheremo automaticamente
            se può essere migliorata in modo sicuro.
          </p>
        </div>

        <label
          className={`upload-box ${
            isDragging ? 'dragging' : ''
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={handleFileChange}
          />

          {!previewUrl ? (
            <div>
              <strong>
                Trascina qui una foto oppure clicca per
                selezionarla
              </strong>

              <p>
                JPG, PNG o WebP
              </p>
            </div>
          ) : (
            <div className="preview-wrapper">
              <img
                src={previewUrl}
                alt="Anteprima della foto selezionata"
                className="preview"
              />

              <button
                type="button"
                className="remove-photo"
                onClick={clearFile}
                aria-label="Rimuovi foto"
              >
                ×
              </button>
            </div>
          )}
        </label>

        {file && (
          <div className="selected-file">
            <span>
              {file.name}
            </span>

            <span>
              {(file.size / 1024 / 1024).toFixed(1)} MB
            </span>
          </div>
        )}

        {error && (
          <p className="upload-error">
            {error}
          </p>
        )}

        {isUploading && (
          <div className="processing-notice">
            <strong>
              Analisi in corso
            </strong>

            <p>
              Per foto molto compromesse i tempi di attesa
              possono arrivare a 1–2 minuti.
            </p>
          </div>
        )}

        <button
          type="button"
          className="primary-button"
          disabled={!file || isUploading}
          onClick={handleAnalyze}
        >
          {isUploading
            ? 'Analisi in corso...'
            : 'Analizza foto'}
        </button>

        {renderResult()}
      </section>
    </main>
  )
}

export default App
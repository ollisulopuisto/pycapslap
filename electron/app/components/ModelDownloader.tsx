import React, { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Check, Download, Loader2 } from 'lucide-react'
import { Button } from './ui/button'

export function ModelDownloader() {
  const [installed, setInstalled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('Checking local model…')

  const refresh = async () => {
    try {
      const ready = await window.rust.call('checkOrukeetInstalled', {})
      setInstalled(Boolean(ready))
      setStatus(ready ? 'Ready for offline transcription' : 'Download the local model to get started')
    } catch {
      setStatus('The local transcription core is unavailable')
    }
  }

  useEffect(() => { void refresh() }, [])

  const install = async () => {
    setBusy(true)
    setStatus('Downloading and verifying the model and runtime…')
    try {
      await window.rust.call('installOrukeet', {})
      setInstalled(true)
      setStatus('Ready for offline transcription')
      toast.success('Orukeet is ready')
    } catch (error: any) {
      const message = error?.message ?? String(error)
      setStatus(`Installation failed: ${message}`)
      toast.error('Could not install Orukeet', { description: message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-3">
      <h3 className="text-base font-medium text-foreground flex items-center gap-2">
        <Download className="w-4 h-4" /> Local transcription
      </h3>
      <p className="text-xs text-muted-foreground">Orukeet multilingual speech recognition · Q8 model · works offline after download</p>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs text-muted-foreground flex items-center gap-1.5">
          {installed && <Check className="w-3.5 h-3.5 text-green-500" />}
          {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          {status}
        </span>
        <Button size="sm" variant="outline" disabled={busy} onClick={install}>
          {busy ? 'Installing…' : installed ? 'Verify / Load' : 'Download'}
        </Button>
      </div>
    </section>
  )
}

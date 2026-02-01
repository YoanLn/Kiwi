import { useCallback, useEffect, useRef, useState } from 'react'

type VoiceStatus = 'idle' | 'connecting' | 'ready' | 'error'

interface UseVoiceChatOptions {
  sessionId: string
  workflowType?: string
  onTranscription?: (role: 'user' | 'assistant', text: string) => void
  onStatus?: (status: string, message?: string) => void
}

const getSpeechRecognition = () => {
  const win = window as typeof window & {
    SpeechRecognition?: any
    webkitSpeechRecognition?: any
  }
  return win.SpeechRecognition || win.webkitSpeechRecognition
}

export const useVoiceChat = ({
  onTranscription,
  onStatus,
}: UseVoiceChatOptions) => {
  const [status, setStatus] = useState<VoiceStatus>('idle')
  const [isRecording, setIsRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const recognitionRef = useRef<any>(null)
  const isRecordingRef = useRef(false)

  const stop = useCallback(() => {
    isRecordingRef.current = false
    setIsRecording(false)
    setStatus('idle')

    const recognition = recognitionRef.current
    recognitionRef.current = null
    if (recognition) {
      recognition.onstart = null
      recognition.onend = null
      recognition.onerror = null
      recognition.onresult = null
      try {
        recognition.stop()
      } catch {
        // Ignore stop failures
      }
    }
  }, [])

  const start = useCallback(() => {
    if (recognitionRef.current || isRecordingRef.current) {
      return
    }

    const RecognitionClass = getSpeechRecognition()
    if (!RecognitionClass) {
      const message = "La reconnaissance vocale n'est pas prise en charge dans ce navigateur"
      setError(message)
      setStatus('error')
      onStatus?.('error', message)
      return
    }

    const recognition = new RecognitionClass()
    recognition.lang = navigator.language || 'fr-FR'
    recognition.interimResults = true
    recognition.continuous = true

    recognition.onstart = () => {
      setStatus('ready')
      onStatus?.('ready')
    }

    recognition.onerror = (event: any) => {
      const message = event?.error
        ? `Erreur de reconnaissance vocale : ${event.error}`
        : 'Erreur de reconnaissance vocale'
      setError(message)
      setStatus('error')
      onStatus?.('error', message)
      isRecordingRef.current = false
      setIsRecording(false)
    }

    recognition.onend = () => {
      if (isRecordingRef.current) {
        setStatus('connecting')
        try {
          recognition.start()
        } catch {
          const message = "La reconnaissance vocale s'est arretee de maniere inattendue"
          setError(message)
          setStatus('error')
          onStatus?.('error', message)
          isRecordingRef.current = false
          setIsRecording(false)
        }
      } else {
        setStatus('idle')
        onStatus?.('idle')
      }
    }

    recognition.onresult = (event: any) => {
      let finalText = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        if (result.isFinal) {
          finalText += result[0].transcript
        }
      }

      finalText = finalText.trim()
      if (finalText) {
        onTranscription?.('user', finalText)
      }
    }

    setError(null)
    setStatus('connecting')
    setIsRecording(true)
    isRecordingRef.current = true
    recognitionRef.current = recognition

    try {
      recognition.start()
    } catch {
      const message = 'Impossible de demarrer la reconnaissance vocale'
      setError(message)
      setStatus('error')
      onStatus?.('error', message)
      isRecordingRef.current = false
      setIsRecording(false)
      recognitionRef.current = null
    }
  }, [onStatus, onTranscription])

  useEffect(() => () => stop(), [stop])

  return {
    status,
    isRecording,
    error,
    start,
    stop,
  }
}

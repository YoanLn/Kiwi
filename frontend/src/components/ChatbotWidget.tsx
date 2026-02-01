import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { Send, Bot, User, X, MessageCircle, Mic, MicOff } from 'lucide-react'
import { chatbotApi } from '../services/api'
import { useVoiceChat } from '../hooks/useVoiceChat'
import type { ChatSource } from '../types'

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
}

export default function ChatbotWidget() {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: "Bonjour ! Je suis votre assistant d'assurance Kiwi. Je peux expliquer les termes d'assurance, repondre aux questions sur le processus de sinistre, et vous guider dans votre contrat. Que souhaitez-vous savoir ?",
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId] = useState(() => `session-${Date.now()}`)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const loadingRef = useRef(false)

  const appendMessage = (role: 'user' | 'assistant', content: string) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1]
      if (last && last.role === role && last.content === content) {
        return prev
      }
      return [...prev, { role, content }]
    })
  }

  const sendMessage = async (messageText: string) => {
    const trimmed = messageText.trim()
    if (!trimmed || loadingRef.current) return

    setInput('')
    appendMessage('user', trimmed)

    try {
      loadingRef.current = true
      setLoading(true)
      const response = await chatbotApi.sendMessage(trimmed, sessionId)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: response.response,
          sources: response.sources,
        },
      ])
    } catch (err) {
      console.error('Failed to send message:', err)
      appendMessage('assistant', 'Desole, une erreur est survenue. Veuillez reessayer.')
    } finally {
      loadingRef.current = false
      setLoading(false)
    }
  }

  const {
    status: voiceStatus,
    error: voiceError,
    start: startVoice,
    stop: stopVoice,
  } = useVoiceChat({
    sessionId,
    onTranscription: (role, text) => {
      if (role === 'user') {
        void sendMessage(text)
      } else {
        appendMessage(role, text)
      }
    },
  })

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    if (isOpen) {
      scrollToBottom()
    }
  }, [messages, isOpen])

  useEffect(() => {
    loadingRef.current = loading
  }, [loading])

  useEffect(() => {
    if (!isOpen && (voiceStatus === 'ready' || voiceStatus === 'connecting')) {
      stopVoice()
    }
  }, [isOpen, voiceStatus, stopVoice])

  const handleSend = async () => {
    await sendMessage(input)
  }

  const handleKeyPress = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const suggestedQuestions = [
    "Qu'est-ce qu'une franchise ?",
    "Combien de temps dure le traitement d'un sinistre ?",
    "Quels documents dois-je fournir ?",
  ]

  const voiceActive = voiceStatus === 'ready' || voiceStatus === 'connecting'
  const voiceLabel =
    voiceStatus === 'ready'
      ? 'Ecoute'
      : voiceStatus === 'connecting'
      ? 'Connexion'
      : 'Desactive'

  return (
    <>
      {/* Chat Widget */}
      {isOpen && (
        <div className="fixed bottom-24 right-6 w-96 h-[600px] bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col z-50 animate-in slide-in-from-bottom-4">
          {/* Header */}
          <div className="bg-primary-600 text-white px-6 py-4 rounded-t-2xl flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center">
                <Bot className="w-6 h-6 text-primary-600" />
              </div>
              <div>
                <h3 className="font-semibold">Assistant Kiwi</h3>
                <p className="text-xs text-primary-100">Toujours la pour vous aider</p>
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="text-white hover:bg-primary-700 rounded-full p-1 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
            {messages.map((message, index) => (
              <div
                key={index}
                className={`flex gap-2 ${
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                {message.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
                    <Bot className="w-5 h-5 text-primary-600" />
                  </div>
                )}

                <div
                  className={`max-w-[75%] rounded-2xl px-4 py-2 ${
                    message.role === 'user'
                      ? 'bg-primary-600 text-white rounded-br-sm'
                      : 'bg-white text-gray-900 rounded-bl-sm shadow-sm'
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{message.content}</p>

                  {message.sources && message.sources.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-gray-200">
                      <p className="text-xs text-gray-500 mb-1">Sources :</p>
                      <div className="flex flex-wrap gap-1">
                        {message.sources.map((source, idx) => {
                          const label = source.label
                          const url = source.url || ''
                          if (url) {
                            return (
                              <a
                                key={idx}
                                href={url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-block px-2 py-0.5 bg-gray-100 rounded text-xs text-gray-600 hover:text-primary-700 hover:underline"
                              >
                                {label}
                              </a>
                            )
                          }
                          return (
                            <span
                              key={idx}
                              className="inline-block px-2 py-0.5 bg-gray-100 rounded text-xs text-gray-600"
                            >
                              {label}
                            </span>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>

                {message.role === 'user' && (
                  <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                    <User className="w-5 h-5 text-gray-600" />
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex gap-2 justify-start">
                <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
                  <Bot className="w-5 h-5 text-primary-600" />
                </div>
                <div className="bg-white rounded-2xl rounded-bl-sm shadow-sm px-4 py-3">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Suggested Questions (show only at start) */}
          {messages.length === 1 && (
            <div className="px-4 pb-2 bg-gray-50">
              <p className="text-xs text-gray-600 mb-2">Essayez de demander :</p>
              <div className="flex flex-col gap-1">
                {suggestedQuestions.map((question, idx) => (
                  <button
                    key={idx}
                    onClick={() => setInput(question)}
                    className="px-3 py-2 bg-white hover:bg-gray-100 rounded-lg text-xs text-left text-gray-700 transition-colors border border-gray-200"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Input */}
          <div className="border-t border-gray-200 p-4 bg-white rounded-b-2xl">
            <div className="flex items-center justify-between text-xs text-gray-500 mb-2">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block w-2 h-2 rounded-full ${
                    voiceStatus === 'ready'
                      ? 'bg-emerald-500'
                      : voiceStatus === 'connecting'
                      ? 'bg-amber-500'
                      : 'bg-gray-300'
                  }`}
                />
                <span>Micro : {voiceLabel}</span>
              </div>
              {voiceError && <span className="text-red-500">{voiceError}</span>}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Posez une question sur l'assurance..."
                className="flex-1 px-4 py-2 border border-gray-300 rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                disabled={loading}
              />
              <button
                onClick={voiceActive ? stopVoice : startVoice}
                className={`border rounded-full p-2 transition-colors ${
                  voiceActive
                    ? 'bg-emerald-500 text-white border-emerald-500 hover:bg-emerald-600'
                    : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-100'
                }`}
                aria-label={voiceActive ? 'Arreter le micro' : 'Demarrer le micro'}
              >
                {voiceActive ? (
                  <MicOff className="w-5 h-5" />
                ) : (
                  <Mic className="w-5 h-5" />
                )}
              </button>
              <button
                onClick={handleSend}
                disabled={!input.trim() || loading}
                className="bg-primary-600 text-white p-2 rounded-full hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-6 right-6 w-14 h-14 bg-primary-600 text-white rounded-full shadow-lg hover:bg-primary-700 transition-all hover:scale-110 flex items-center justify-center z-50"
        aria-label="Ouvrir le chat"
      >
        {isOpen ? (
          <X className="w-6 h-6" />
        ) : (
          <MessageCircle className="w-6 h-6" />
        )}
      </button>

      {/* Notification Badge (optional - can show unread count) */}
      {!isOpen && (
        <div className="fixed bottom-[4.5rem] right-[4.5rem] w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center z-50 animate-pulse">
          !
        </div>
      )}
    </>
  )
}

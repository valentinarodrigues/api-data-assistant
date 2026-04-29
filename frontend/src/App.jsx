import { useState, useEffect, useRef } from 'react'
import ChatMessage from './components/ChatMessage'
import FieldSidebar from './components/FieldSidebar'

const SUGGESTED = [
  'Is customer email available?',
  'Which API has shipping tracking info?',
  'Can I get a customer\'s loyalty tier?',
  'Is product stock quantity available?',
  'Where can I find the order total?',
  'Is billing address available in any API?',
]

export default function App() {
  const [messages, setMessages]     = useState([])
  const [fields, setFields]         = useState([])
  const [input, setInput]           = useState('')
  const [streaming, setStreaming]   = useState(false)
  const [ollamaOk, setOllamaOk]    = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  useEffect(() => {
    fetch('/health')
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(() => setOllamaOk(true))
      .catch(() => setOllamaOk(false))

    fetch('/fields')
      .then(r => r.json())
      .then(d => setFields(d.fields ?? []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send(question) {
    const q = (question ?? input).trim()
    if (!q || streaming) return
    setInput('')

    setMessages(prev => [
      ...prev,
      { role: 'user',      content: q },
      { role: 'assistant', content: '', streaming: true },
    ])
    setStreaming(true)

    try {
      const resp = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      })

      const reader  = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer    = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6)
          if (payload === '[DONE]') break
          const chunk = JSON.parse(payload)
          if (chunk.error) {
            setMessages(prev => {
              const copy = [...prev]
              copy[copy.length - 1] = { role: 'assistant', content: `⚠️ ${chunk.error}`, streaming: false }
              return copy
            })
            break
          }
          if (chunk.token) {
            setMessages(prev => {
              const copy = [...prev]
              const last = copy[copy.length - 1]
              copy[copy.length - 1] = { ...last, content: last.content + chunk.token }
              return copy
            })
          }
        }
      }
    } catch {
      setMessages(prev => {
        const copy = [...prev]
        copy[copy.length - 1] = { role: 'assistant', content: '⚠️ Could not reach the server.', streaming: false }
        return copy
      })
    } finally {
      setMessages(prev => {
        const copy = [...prev]
        if (copy[copy.length - 1]?.streaming) {
          copy[copy.length - 1] = { ...copy[copy.length - 1], streaming: false }
        }
        return copy
      })
      setStreaming(false)
      inputRef.current?.focus()
    }
  }

  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div className="flex h-full bg-[#0f1117]">
      {sidebarOpen && <FieldSidebar fields={fields} />}

      <div className="flex-1 flex flex-col min-w-0">

        {/* Header */}
        <header className="flex items-center gap-3 px-4 py-3 border-b border-slate-800 bg-[#0b0d14]">
          <button
            onClick={() => setSidebarOpen(v => !v)}
            className="text-slate-500 hover:text-slate-300 transition-colors"
            title="Toggle field list"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-violet-600 flex items-center justify-center flex-shrink-0">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <span className="font-semibold text-slate-100 text-sm">API Data Assistant</span>
          </div>

          <div className="ml-auto flex items-center gap-2">
            {ollamaOk === null && <span className="text-xs text-slate-500">Checking Ollama…</span>}
            {ollamaOk === true  && (
              <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                Ollama connected
              </span>
            )}
            {ollamaOk === false && (
              <span className="flex items-center gap-1.5 text-xs text-red-400">
                <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
                Ollama offline
              </span>
            )}
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6 space-y-5">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-6 text-center">
              <div>
                <h1 className="text-2xl font-semibold text-slate-100 mb-2">
                  What data are you looking for?
                </h1>
                <p className="text-slate-500 text-sm max-w-md">
                  Ask whether a field exists across any of the APIs. I'll tell you which one has it.
                </p>
              </div>
              <div className="flex flex-wrap justify-center gap-2 max-w-xl">
                {SUGGESTED.map(s => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    disabled={streaming || ollamaOk === false}
                    className="text-xs px-3 py-2 rounded-full border border-slate-700 text-slate-400
                               hover:border-violet-500 hover:text-violet-300 transition-colors disabled:opacity-40"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m, i) => (
              <ChatMessage key={i} role={m.role} content={m.content} streaming={m.streaming} />
            ))
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="px-4 py-4 border-t border-slate-800 bg-[#0b0d14]">
          <div className="flex gap-3 items-end max-w-4xl mx-auto">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={onKey}
              disabled={streaming || ollamaOk === false}
              placeholder={ollamaOk === false ? 'Start Ollama to use the assistant…' : 'Ask about any field across all APIs…'}
              className="flex-1 resize-none rounded-xl bg-slate-800 text-slate-100 placeholder-slate-500
                         text-sm px-4 py-3 outline-none focus:ring-1 focus:ring-violet-500
                         disabled:opacity-40 leading-relaxed"
              style={{ maxHeight: '8rem', overflowY: 'auto' }}
            />
            <button
              onClick={() => send()}
              disabled={streaming || !input.trim() || ollamaOk === false}
              className="w-10 h-10 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-40
                         flex items-center justify-center transition-colors flex-shrink-0"
            >
              {streaming ? (
                <svg className="w-4 h-4 text-white animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                </svg>
              ) : (
                <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              )}
            </button>
          </div>
          <p className="text-center text-slate-600 text-xs mt-2">Enter to send · Shift+Enter for new line</p>
        </div>
      </div>
    </div>
  )
}

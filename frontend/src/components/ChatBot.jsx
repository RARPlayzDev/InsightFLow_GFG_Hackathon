import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { sendChatMessage } from '../utils/api'

export default function ChatBot({ inline = false, context = null }) {
  const [isOpen, setIsOpen] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const toggleChat = () => {
    setIsOpen(!isOpen)
    if (isOpen) setIsExpanded(false)
  }
  
  const toggleExpand = () => setIsExpanded(!isExpanded)

  const handleSend = async () => {
    if (!input.trim()) return
    const userMsg = input.trim()
    setInput('')
    const newMessages = [...messages, { role: 'user', content: userMsg }]
    setMessages(newMessages)
    setLoading(true)

    try {
      const response = await sendChatMessage(userMsg, messages, context)
      setMessages([...newMessages, { role: 'assistant', content: response.response }])
    } catch (err) {
      setMessages([...newMessages, { role: 'assistant', content: `Error: ${err.message}` }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const showChat = inline || isOpen

  return (
    <div className={
        inline ? 'chatbot-inline' : 
        `chatbot-wrapper ${isOpen ? 'open' : ''} ${isExpanded ? 'expanded' : ''}`
      } 
      style={inline ? { display: 'flex', flexDirection: 'column', height: '100%', width: '100%' } : {}}
    >
      {!inline && !isOpen && (
        <button className="chatbot-toggle-btn" onClick={toggleChat} title="Need help? Ask the Data Assistant">
          💬 Chat
        </button>
      )}
      {showChat && (
        <div className={
            inline ? 'chatbot-window inline' : 
            `chatbot-window ${isExpanded ? 'expanded' : ''}`
          } 
          style={inline ? { position: 'static', width: '100%', height: '100%', boxShadow: 'none', borderRadius: 0, border: 'none', display: 'flex', flexDirection: 'column' } : {}}
        >
          <div className="chatbot-header" style={inline ? { borderRadius: 0 } : {}}>
            <div className="chatbot-header-info">
               <span className="chatbot-header-dot" />
               <h4>Data Assistant</h4>
            </div>
            <div className="chatbot-header-actions">
              {!inline && (
                <button 
                  className="chatbot-action-btn" 
                  onClick={toggleExpand} 
                  title={isExpanded ? "Shrink" : "Expand"}
                >
                  {isExpanded ? '❐' : '⬜'}
                </button>
              )}
              {!inline && <button className="chatbot-close-btn" onClick={toggleChat} title="Close">✕</button>}
            </div>
          </div>
          <div className="chatbot-messages">
            {messages.length === 0 && (
              <div className="chatbot-empty">
                <div style={{ fontSize: '2rem', marginBottom: '1rem', opacity: 0.5 }}>🤖</div>
                <h5>Welcome to InsightFlow Analyst!</h5>
                <p>Ask me about your dataset schema or how to formulate your questions!</p>
              </div>
            )}
            {messages.map((msg, idx) => (
              <div key={idx} className={`chatbot-message ${msg.role}`}>
                {msg.role === 'assistant' ? (
                  <div className="assistant-content">
                    <ReactMarkdown>
                      {typeof msg.content === 'string' 
                        ? msg.content 
                        : (msg.content ? JSON.stringify(msg.content, null, 2) : 'No response content')}
                    </ReactMarkdown>
                  </div>
                ) : (
                  typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content)
                )}
              </div>
            ))}
            {loading && (
              <div className="chatbot-message assistant">
                <div className="chatbot-typing-container">
                  <span className="dot" />
                  <span className="dot" />
                  <span className="dot" />
                  <span className="chatbot-typing-text">Analysing...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
          <div className="chatbot-input-area">
            <textarea
              className="chatbot-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question..."
              rows={1}
            />
            <button className="btn btn-primary chatbot-send-btn" onClick={handleSend} disabled={loading || !input.trim()}>
              ➤
            </button>
          </div>
        </div>
      )
      }
    </div>
  )
}

import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { healthCheck } from './utils/api'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import History from './pages/History'
import ThemeToggle from './components/ThemeToggle'

function Navbar({ health }) {
  function statusColor() {
    if (!health) return 'error'
    if (!health.groq_key_looks_valid) return 'warn'
    return ''
  }

  return (
    <nav className="navbar">
      <NavLink to="/" className="navbar-brand">
        <svg width="160" height="36" viewBox="0 0 680 220" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="nb-card" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%"   stopColor="#e8f4ff" stopOpacity="0.95"/>
              <stop offset="100%" stopColor="#d0f5ec" stopOpacity="0.9"/>
            </linearGradient>
            <linearGradient id="nb-stroke" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%"   stopColor="#1a4fa0"/>
              <stop offset="60%"  stopColor="#0ea87a"/>
              <stop offset="100%" stopColor="#00c896"/>
            </linearGradient>
            <linearGradient id="nb-bar" x1="0%" y1="100%" x2="0%" y2="0%">
              <stop offset="0%"   stopColor="#1a7fd4"/>
              <stop offset="100%" stopColor="#00c8a0"/>
            </linearGradient>
            <linearGradient id="nb-bulb" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%"   stopColor="#ffd84d"/>
              <stop offset="100%" stopColor="#f09020"/>
            </linearGradient>
            <linearGradient id="nb-bubble" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%"   stopColor="#1a6fd4"/>
              <stop offset="100%" stopColor="#1a4fa0"/>
            </linearGradient>
            <linearGradient id="nb-insight" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%"   stopColor="#0d2d6b"/>
              <stop offset="100%" stopColor="#1a4fa0"/>
            </linearGradient>
            <linearGradient id="nb-flow" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%"   stopColor="#0ea87a"/>
              <stop offset="100%" stopColor="#00c896"/>
            </linearGradient>
            <clipPath id="nb-clip">
              <rect x="2" y="14" width="148" height="114" rx="14"/>
            </clipPath>
          </defs>

          {/* Card */}
          <rect x="2" y="14" width="148" height="114" rx="14"
                fill="url(#nb-card)" stroke="url(#nb-stroke)" strokeWidth="1.5"/>

          {/* Wave inside card */}
          <path d="M2 90 Q30 78 62 90 Q94 102 126 90 Q140 84 150 87"
                fill="none" stroke="url(#nb-stroke)" strokeWidth="1.5" strokeLinecap="round"
                clipPath="url(#nb-clip)"/>

          {/* Bars */}
          <rect x="16" y="62" width="7"  height="24" rx="2" fill="url(#nb-bar)" opacity="0.9"/>
          <rect x="27" y="54" width="7"  height="32" rx="2" fill="url(#nb-bar)" opacity="0.9"/>
          <rect x="38" y="45" width="7"  height="41" rx="2" fill="url(#nb-bar)" opacity="0.9"/>

          {/* Line chart */}
          <polyline points="56,82 66,68 76,74 88,60"
                    fill="none" stroke="#1a7fd4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <circle cx="56" cy="82" r="2.5" fill="#1a7fd4"/>
          <circle cx="66" cy="68" r="2.5" fill="#1a7fd4"/>
          <circle cx="76" cy="74" r="2.5" fill="#1a7fd4"/>
          <circle cx="88" cy="60" r="2.5" fill="#1a7fd4"/>

          {/* Pie chart upper-right */}
          <circle cx="118" cy="60" r="18" fill="none" stroke="#0ea87a" strokeWidth="1.2"/>
          <path d="M118 60 L118 42 A18 18 0 0 1 136 60 Z" fill="#1a7fd4" opacity="0.8"/>
          <path d="M118 60 L136 60 A18 18 0 0 1 124 77 Z" fill="#0ea87a" opacity="0.75"/>

          {/* Pie chart lower-right */}
          <circle cx="120" cy="97" r="13" fill="none" stroke="#1a7fd4" strokeWidth="1.2"/>
          <path d="M120 97 L120 84 A13 13 0 0 1 133 97 Z" fill="#1a7fd4" opacity="0.7"/>
          <path d="M120 97 L133 97 A13 13 0 0 1 120 110 Z" fill="#0ea87a" opacity="0.65"/>

          {/* Chat bubble */}
          <path d="M28 0 Q14 0 14 10 L14 32 Q14 42 28 42 L46 42 L43 50 L56 42 L72 42 Q86 42 86 32 L86 10 Q86 0 72 0 Z"
                fill="url(#nb-bubble)"/>
          <text x="50" y="27" fontFamily="'Segoe UI',Arial,sans-serif" fontSize="14"
                fontWeight="800" fill="white" textAnchor="middle">I_</text>

          {/* Bulb */}
          <line x1="136" y1="4"  x2="136" y2="0"  stroke="#ffd84d" strokeWidth="1.5" strokeLinecap="round"/>
          <line x1="145" y1="8"  x2="149" y2="4"  stroke="#ffd84d" strokeWidth="1.3" strokeLinecap="round"/>
          <line x1="127" y1="8"  x2="123" y2="4"  stroke="#ffd84d" strokeWidth="1.3" strokeLinecap="round"/>
          <circle cx="136" cy="18" r="11" fill="url(#nb-bulb)"/>
          <rect x="132" y="27" width="8" height="3" rx="1" fill="#c07030" opacity="0.8"/>

          {/* Wordmark */}
          <text x="162" y="76" fontFamily="'Segoe UI',Arial,sans-serif"
                fontSize="52" fontWeight="900" letterSpacing="-1">
            <tspan fill="url(#nb-insight)">Insight</tspan>
            <tspan fill="url(#nb-flow)">Flow</tspan>
          </text>

          {/* Tagline */}
          <text x="162" y="100" fontFamily="'Segoe UI',Arial,sans-serif"
                fontSize="11" fontWeight="600" fill="#5a7090" letterSpacing="1.8">
            SMART DASHBOARDS FROM PLAIN ENGLISH
          </text>
        </svg>
      </NavLink>

      <div className="navbar-center">
        <NavLink to="/dashboard" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
          Dashboard
        </NavLink>
        <NavLink to="/upload" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
          Upload
        </NavLink>
        <NavLink to="/history" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
          History
        </NavLink>
      </div>

      <div className="navbar-right">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.775rem', color: 'var(--text-muted)' }}>
          <span className={`status-dot ${statusColor()}`} />
          <span>
            {!health ? 'Connecting…'
              : !health.groq_key_looks_valid ? 'API key invalid'
              : 'System ready'}
          </span>
        </div>
        <ThemeToggle />
      </div>
    </nav>
  )
}

function AppRoutes({ health }) {
  return (
    <>
      <Navbar health={health} />
      <Routes>
        <Route path="/"          element={<Landing />} />
        <Route path="/dashboard" element={<Dashboard health={health} />} />
        <Route path="/upload"    element={<Upload />} />
        <Route path="/history"   element={<History />} />
      </Routes>
    </>
  )
}

export default function App() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    async function poll() {
      try {
        const h = await healthCheck()
        setHealth(h)
      } catch {
        setHealth(null)
      }
    }
    poll()
    const interval = setInterval(poll, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <BrowserRouter>
      <AppRoutes health={health} />
    </BrowserRouter>
  )
}
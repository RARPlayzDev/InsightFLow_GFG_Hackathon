import { useEffect, useState } from 'react';

export default function ThemeToggle() {
  const [theme, setTheme] = useState(localStorage.getItem('insightflow_theme') || 'light');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('insightflow_theme', theme);
  }, [theme]);

  // Make sure not to render undefined values before mounting in Next.js (if applicable, but we have Vite)
  return (
    <button
      className="btn btn-ghost btn-sm btn-icon"
      onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
      title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
      style={{ fontSize: '1.2rem', padding: '4px 8px' }}
    >
      {theme === 'light' ? '🌙' : '☀️'}
    </button>
  );
}

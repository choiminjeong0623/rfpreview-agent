import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tokens.css'
import './mockup/Main.css'
import './ui/ui.css'
import App from './App.tsx'
import { SessionProvider } from './shell/session'
import { ToastProvider } from './ui/Toasts'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <SessionProvider>
      <ToastProvider>
        <App />
      </ToastProvider>
    </SessionProvider>
  </StrictMode>,
)

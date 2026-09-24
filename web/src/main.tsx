import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './features/auth/AuthProvider'
import { I18nProvider } from './i18n'
import './index.css'

// Provider 的嵌套顺序：I18n 在最外——报错文案、空态提示都要靠它；
// Auth 在 Router 里面，因为它内部的登录/登出要跳转（`useNavigate`）。
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </I18nProvider>
  </React.StrictMode>,
)

import { createRoot } from 'react-dom/client'
import App from './App'
import AdminConsole from './AdminConsole'

createRoot(document.getElementById('root')!).render(window.location.pathname === '/admin' ? <AdminConsole /> : <App />)
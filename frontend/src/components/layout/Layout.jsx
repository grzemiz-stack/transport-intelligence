import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header from './Header'

export default function Layout() {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', width: '100%' }}>
      <Sidebar />
      <div style={{ marginLeft: 256, flex: '1 1 0%', minWidth: 0, display: 'flex', flexDirection: 'column', width: 'calc(100% - 256px)' }}>
        <Header />
        <main style={{ flex: '1 1 0%', minWidth: 0, padding: 24, overflowX: 'hidden', overflowY: 'auto' }}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}

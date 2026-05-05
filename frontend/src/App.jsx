import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import ErrorBoundary from './components/common/ErrorBoundary'
import LoadingSpinner from './components/common/LoadingSpinner'
import { isAuthenticated } from './api/auth'

const LoginPage = lazy(() => import('./pages/LoginPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const EventsPage = lazy(() => import('./pages/EventsPage'))
const EventDetailPage = lazy(() => import('./pages/EventDetailPage'))
const AgentsPage = lazy(() => import('./pages/AgentsPage'))
const CompaniesPage = lazy(() => import('./pages/CompaniesPage'))
const CompanyDetailPage = lazy(() => import('./pages/CompanyDetailPage'))
const AlertsPage = lazy(() => import('./pages/AlertsPage'))
const ReportsPage = lazy(() => import('./pages/ReportsPage'))
const MapPage = lazy(() => import('./pages/MapPage'))

function SuspenseWrap({ children }) {
  return <Suspense fallback={<LoadingSpinner />}>{children}</Suspense>
}

function ProtectedRoute({ children }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  return children
}

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<SuspenseWrap><LoginPage /></SuspenseWrap>} />
        <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
          <Route path="/" element={<SuspenseWrap><DashboardPage /></SuspenseWrap>} />
          <Route path="/events" element={<SuspenseWrap><EventsPage /></SuspenseWrap>} />
          <Route path="/events/:id" element={<SuspenseWrap><EventDetailPage /></SuspenseWrap>} />
          <Route path="/map" element={<SuspenseWrap><MapPage /></SuspenseWrap>} />
          <Route path="/agents" element={<SuspenseWrap><AgentsPage /></SuspenseWrap>} />
          <Route path="/companies" element={<SuspenseWrap><CompaniesPage /></SuspenseWrap>} />
          <Route path="/companies/:id" element={<SuspenseWrap><CompanyDetailPage /></SuspenseWrap>} />
          <Route path="/alerts" element={<SuspenseWrap><AlertsPage /></SuspenseWrap>} />
          <Route path="/reports" element={<SuspenseWrap><ReportsPage /></SuspenseWrap>} />
        </Route>
      </Routes>
    </ErrorBoundary>
  )
}

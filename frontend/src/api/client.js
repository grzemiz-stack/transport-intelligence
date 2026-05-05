import axios from 'axios'

const TOKEN_KEY = 'ti_access_token'

const client = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// Request interceptor — attach Bearer token
client.interceptors.request.use((config) => {
  const token = sessionStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor — redirect to /login on 401
client.interceptors.response.use(
  (res) => res,
  (err) => {
    console.error('[API]', err.response?.status, err.config?.url, err.message)
    if (err.response?.status === 401 && !err.config?.url?.includes('/auth/login')) {
      sessionStorage.removeItem(TOKEN_KEY)
      sessionStorage.removeItem('ti_user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default client

// Dashboard
export const fetchDashboardOverview = () => client.get('/dashboard/overview')
export const fetchDashboardMap = () => client.get('/dashboard/map')
export const fetchDashboardTrends = () => client.get('/dashboard/trends')
export const fetchDashboardFinancial = () => client.get('/dashboard/financial')

// Events
export const fetchEvents = (params) => client.get('/events/', { params })
export const fetchEvent = (id) => client.get(`/events/${id}`)
export const fetchEventStats = () => client.get('/events/stats')
export const fetchEventTimeline = (params) => client.get('/events/timeline', { params })
export const translateEvent = (id) => client.post(`/events/${id}/translate`)

// Agents
export const fetchAgentStatus = () => client.get('/agents/status')
export const fetchAgentHealth = () => client.get('/agents/health')
export const fetchAgentLogs = () => client.get('/agents/logs')
export const fetchCountryAgents = (cc) => client.get(`/agents/status/${cc}`)
export const startCountryAgents = (cc) => client.post(`/agents/${cc}/start`)
export const stopCountryAgents = (cc) => client.post(`/agents/${cc}/stop`)
export const restartCountryAgents = (cc) => client.post(`/agents/${cc}/restart`)
export const restartAgent = (cc, type) => client.post(`/agents/${cc}/${type}/restart`)

// Companies
export const fetchCompanies = (params) => client.get('/companies/', { params })
export const fetchCompany = (id) => client.get(`/companies/${id}`)
export const fetchCompaniesAtRisk = () => client.get('/companies/at-risk')
export const fetchCompanyTimeline = (id) => client.get(`/companies/${id}/timeline`)

// Alerts
export const fetchAlerts = (params) => client.get('/alerts/', { params })
export const fetchAlert = (id) => client.get(`/alerts/${id}`)
export const fetchActiveAlerts = () => client.get('/alerts/active')
export const fetchAlertStats = () => client.get('/alerts/stats')
export const resolveAlert = (id, data = {}) => client.post(`/alerts/${id}/resolve`, data)

// Reports
export const fetchReports = () => client.get('/reports/')
export const fetchReport = (id) => client.get(`/reports/${id}`)
export const generateReport = (data) => client.post('/reports/generate', data)
export const fetchReportSchedules = () => client.get('/reports/schedule')

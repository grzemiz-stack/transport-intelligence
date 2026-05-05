/**
 * Modul autentykacji — login, logout, token management.
 */
import client from './client'

const TOKEN_KEY = 'ti_access_token'
const USER_KEY = 'ti_user'

export async function login(email, password) {
  const res = await client.post('/auth/login', { email, password })
  const { access_token, user } = res.data
  sessionStorage.setItem(TOKEN_KEY, access_token)
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
  return { token: access_token, user }
}

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function getUser() {
  const raw = sessionStorage.getItem(USER_KEY)
  return raw ? JSON.parse(raw) : null
}

export function isAuthenticated() {
  return !!getToken()
}

export function logout() {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
  window.location.href = '/login'
}

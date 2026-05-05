export const SEVERITY_COLORS = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#22c55e',
  INFO: '#3b82f6',
}

export const SEVERITY_BG = {
  CRITICAL: 'bg-red-500/20 text-red-400 border-red-500/30',
  HIGH: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  MEDIUM: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  LOW: 'bg-green-500/20 text-green-400 border-green-500/30',
  INFO: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  // Polish severity labels
  KRYTYCZNY: 'bg-red-500/20 text-red-400 border-red-500/30',
  WYSOKI: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  'ŚREDNI': 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  NISKI: 'bg-green-500/20 text-green-400 border-green-500/30',
}

export const STATUS_BG = {
  active: 'bg-green-500/20 text-green-400 border-green-500/30',
  running: 'bg-green-500/20 text-green-400 border-green-500/30',
  stopped: 'bg-red-500/20 text-red-400 border-red-500/30',
  error: 'bg-red-500/20 text-red-400 border-red-500/30',
  warning: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  resolved: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
  pending: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  // Polish status/financial labels
  AKTYWNE: 'bg-green-500/20 text-green-400 border-green-500/30',
  'ROZWIĄZANE': 'bg-slate-500/20 text-slate-400 border-slate-500/30',
  'UPADŁOŚĆ': 'bg-red-500/20 text-red-400 border-red-500/30',
  KRYTYCZNY: 'bg-red-500/20 text-red-400 border-red-500/30',
  'OSTRZEŻENIE': 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  RESTRUKTURYZACJA: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  ZDROWA: 'bg-green-500/20 text-green-400 border-green-500/30',
  OK: 'bg-green-500/20 text-green-400 border-green-500/30',
  NIEZNANY: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
}

export const EVENT_TYPES = [
  'theft_cargo', 'theft_fuel', 'theft_vehicle', 'damage', 'delay',
  'strike', 'road_blockade', 'accident', 'fraud', 'smuggling',
  'payment_issue', 'bankruptcy', 'license_revoked', 'restructuring', 'other',
]

export const EVENT_TYPE_LABELS = {
  theft_cargo: 'Kradzież ładunku',
  theft_fuel: 'Kradzież paliwa',
  theft_vehicle: 'Kradzież pojazdu',
  damage: 'Uszkodzenie',
  delay: 'Opóźnienie',
  strike: 'Strajk',
  road_blockade: 'Blokada drogi',
  accident: 'Wypadek',
  fraud: 'Oszustwo',
  smuggling: 'Przemyt',
  payment_issue: 'Problem płatniczy',
  bankruptcy: 'Upadłość',
  license_revoked: 'Cofnięcie licencji',
  restructuring: 'Restrukturyzacja',
  route_closure: 'Zamknięcie trasy',
  other: 'Inne',
}

export const SEVERITY_LABELS = {
  CRITICAL: 'KRYTYCZNY',
  HIGH: 'WYSOKI',
  MEDIUM: 'ŚREDNI',
  LOW: 'NISKI',
  INFO: 'INFO',
}

export const FINANCIAL_STATUS_LABELS = {
  BANKRUPT: 'UPADŁOŚĆ',
  CRITICAL: 'KRYTYCZNY',
  WARNING: 'OSTRZEŻENIE',
  RESTRUCTURING: 'RESTRUKTURYZACJA',
  HEALTHY: 'ZDROWA',
  OK: 'OK',
  UNKNOWN: 'NIEZNANY',
}

export const COUNTRIES = {
  PL: { name: 'Poland', flag: '\u{1F1F5}\u{1F1F1}' },
  DE: { name: 'Germany', flag: '\u{1F1E9}\u{1F1EA}' },
  FR: { name: 'France', flag: '\u{1F1EB}\u{1F1F7}' },
  CZ: { name: 'Czech Republic', flag: '\u{1F1E8}\u{1F1FF}' },
  SK: { name: 'Slovakia', flag: '\u{1F1F8}\u{1F1F0}' },
  HU: { name: 'Hungary', flag: '\u{1F1ED}\u{1F1FA}' },
  RO: { name: 'Romania', flag: '\u{1F1F7}\u{1F1F4}' },
  BG: { name: 'Bulgaria', flag: '\u{1F1E7}\u{1F1EC}' },
  HR: { name: 'Croatia', flag: '\u{1F1ED}\u{1F1F7}' },
  SI: { name: 'Slovenia', flag: '\u{1F1F8}\u{1F1EE}' },
  AT: { name: 'Austria', flag: '\u{1F1E6}\u{1F1F9}' },
  NL: { name: 'Netherlands', flag: '\u{1F1F3}\u{1F1F1}' },
  BE: { name: 'Belgium', flag: '\u{1F1E7}\u{1F1EA}' },
  IT: { name: 'Italy', flag: '\u{1F1EE}\u{1F1F9}' },
  ES: { name: 'Spain', flag: '\u{1F1EA}\u{1F1F8}' },
  PT: { name: 'Portugal', flag: '\u{1F1F5}\u{1F1F9}' },
  SE: { name: 'Sweden', flag: '\u{1F1F8}\u{1F1EA}' },
  NO: { name: 'Norway', flag: '\u{1F1F3}\u{1F1F4}' },
  DK: { name: 'Denmark', flag: '\u{1F1E9}\u{1F1F0}' },
  FI: { name: 'Finland', flag: '\u{1F1EB}\u{1F1EE}' },
  GB: { name: 'United Kingdom', flag: '\u{1F1EC}\u{1F1E7}' },
  IE: { name: 'Ireland', flag: '\u{1F1EE}\u{1F1EA}' },
  CH: { name: 'Switzerland', flag: '\u{1F1E8}\u{1F1ED}' },
  GR: { name: 'Greece', flag: '\u{1F1EC}\u{1F1F7}' },
  TR: { name: 'Turkey', flag: '\u{1F1F9}\u{1F1F7}' },
  RS: { name: 'Serbia', flag: '\u{1F1F7}\u{1F1F8}' },
  BA: { name: 'Bosnia', flag: '\u{1F1E7}\u{1F1E6}' },
  LT: { name: 'Lithuania', flag: '\u{1F1F1}\u{1F1F9}' },
  LV: { name: 'Latvia', flag: '\u{1F1F1}\u{1F1FB}' },
  EE: { name: 'Estonia', flag: '\u{1F1EA}\u{1F1EA}' },
  UA: { name: 'Ukraine', flag: '\u{1F1FA}\u{1F1E6}' },
}

export const CHART_COLORS = ['#3b82f6', '#ef4444', '#f97316', '#eab308', '#22c55e', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16', '#f43f5e']

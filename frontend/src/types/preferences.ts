export type CurrencyCode = 'INR'
export type ThemeMode = 'light' | 'dark'

export interface UserPreferences {
  currency: CurrencyCode
  theme: ThemeMode
  budgetAlerts: boolean
  weeklySummary: boolean
}

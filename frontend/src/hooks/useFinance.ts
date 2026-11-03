import { useContext } from 'react'
import { FinanceContext } from './financeContext'

export function useFinance() {
  const context = useContext(FinanceContext)
  if (!context) throw new Error('useFinance must be used inside FinanceProvider.')
  return context
}

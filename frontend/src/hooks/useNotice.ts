import { useCallback, useEffect, useRef, useState } from 'react'

export function useNotice() {
  const [notice, setNotice] = useState('')
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showNotice = useCallback((message: string) => {
    setNotice(message)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => setNotice(''), 3500)
  }, [])

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current)
  }, [])

  return { notice, showNotice }
}

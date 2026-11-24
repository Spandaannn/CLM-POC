import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Spinner } from './Spinner'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  loading?: boolean
  children: ReactNode
}

export function Button({
  variant = 'primary',
  loading = false,
  disabled,
  type = 'button',
  className = '',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={`button button--${variant} ${className}`.trim()}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading && <Spinner size={16} label="Working" />}
      <span>{children}</span>
    </button>
  )
}

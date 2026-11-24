interface SpinnerProps {
  size?: number
  label?: string
}

/** An accessible, CSS-animated loading indicator. */
export function Spinner({ size = 24, label = 'Loading' }: SpinnerProps) {
  return (
    <span className="spinner-wrap" role="status">
      <svg
        className="spinner"
        width={size}
        height={size}
        viewBox="0 0 24 24"
        aria-hidden="true"
        focusable="false"
      >
        <circle
          cx="12"
          cy="12"
          r="9"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          strokeOpacity="0.22"
        />
        <path
          d="M21 12a9 9 0 0 0-9-9"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </svg>
      <span className="visually-hidden">{label}</span>
    </span>
  )
}

export function PageLoader({ message = 'Loading...' }: { message?: string }) {
  return (
    <main className="page-loader" aria-live="polite">
      <Spinner size={36} label={message} />
      <p>{message}</p>
    </main>
  )
}

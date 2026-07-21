import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
  /** Optional fallback — receives the error so pages can render context-aware UI. */
  fallback?: (error: Error, reset: () => void) => ReactNode
}

interface State {
  error: Error | null
}

/**
 * Catches render-time errors that would otherwise crash the React tree and
 * produce a blank white screen. Wrap routes or layout shells to guarantee
 * the user always sees *something*.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  private reset = () => {
    this.setState({ error: null })
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    if (this.props.fallback) {
      return this.props.fallback(error, this.reset)
    }

    // Default fallback — minimal, matches the app's dark theme.
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg p-6">
        <div className="max-w-md text-center space-y-4">
          <h1 className="text-xl font-semibold text-text">Algo salio mal</h1>
          <p className="text-sm text-text-secondary">
            Ocurrio un error inesperado. Intenta recargar la pagina.
          </p>
          <pre className="text-xs text-text-muted bg-bg-subtle rounded-lg p-3 overflow-x-auto text-left">
            {error.message}
          </pre>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-primary text-white hover:opacity-90 transition-opacity"
          >
            Recargar pagina
          </button>
        </div>
      </div>
    )
  }
}

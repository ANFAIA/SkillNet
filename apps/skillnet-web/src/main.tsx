import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ApiError } from './api/client'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Never retry auth/permission/not-found errors.
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
          return false
        }
        return failureCount < 3
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: true,
    },
    mutations: {
      retry: false,
    },
  },
})

// Global 401 handler: clear cache and redirect to login. Lives here so no page
// component needs auth logic. Guard against redirect loops while already on /login.
function handleGlobalError(error: unknown) {
  if (error instanceof ApiError && error.status === 401) {
    if (window.location.pathname !== '/login') {
      queryClient.clear()
      window.location.href = '/login'
    }
  }
}

queryClient.getQueryCache().config.onError = handleGlobalError
queryClient.getMutationCache().config.onError = handleGlobalError

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)

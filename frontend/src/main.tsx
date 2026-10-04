import '@fontsource-variable/figtree'
import '@fontsource-variable/newsreader'
import '@fontsource-variable/newsreader/wght-italic.css'
import {
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ApiError, isSignedOut } from './api/client'
import { queryKeys } from './api/hooks'
import App from './App.tsx'
import { ErrorBoundary } from './components/ErrorBoundary'
import './index.css'

const MAX_RETRIES = 2

const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({
    // An expired session anywhere sends Luis back to the sign-in screen (ui.md §4).
    onError: (error) => {
      if (isSignedOut(error)) queryClient.setQueryData(queryKeys.me, null)
    },
  }),
  defaultOptions: {
    queries: {
      // Retry only what may succeed later: network trouble and server errors.
      retry: (failures, error) =>
        failures < MAX_RETRIES &&
        !(error instanceof ApiError && error.status < 500 && error.status > 0),
      refetchOnWindowFocus: false,
    },
  },
})

const root = document.getElementById('root')
if (!root) {
  throw new Error('index.html must contain <div id="root">')
}

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </MotionConfig>
    </QueryClientProvider>
  </StrictMode>,
)

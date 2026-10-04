// Never a blank page (OWASP A10): if rendering fails, say so plainly and offer a reload.
import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // The error type and where it happened only: messages and props can carry member data.
    console.error('render_failed', {
      error: error.name,
      where: componentNames(info.componentStack),
    })
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children
    return (
      <div
        role="alert"
        className="flex flex-col items-center gap-4 px-6 py-16 text-center"
      >
        <p className="font-serif text-2xl">
          Something went wrong. Reload the page.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-md bg-navy px-4 py-2 font-medium text-white hover:opacity-90"
        >
          Reload
        </button>
      </div>
    )
  }
}

function componentNames(stack: string | null | undefined): string[] {
  const names = (stack ?? '').match(/at (\w+)/g) ?? []
  return names.slice(0, 5).map((frame) => frame.replace('at ', ''))
}

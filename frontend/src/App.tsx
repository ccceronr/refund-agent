import { useMe } from './api/hooks'
import { SignIn } from './components/SignIn'
import { Workspace } from './components/Workspace'

function App() {
  const me = useMe()
  if (me.isPending) return <main className="min-h-screen" aria-busy="true" />
  if (!me.data) return <SignIn />
  return <Workspace staff={me.data} />
}

export default App

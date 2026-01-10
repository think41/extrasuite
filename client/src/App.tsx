import { useEffect, useState } from 'react'
import './App.css'

interface UserInfo {
  email: string
  name: string
  picture: string | null
  hd: string | null
}

interface MagicToken {
  token: string
  expires_at: string
  command_macos: string
  command_linux: string
  command_windows: string
}

interface ServiceAccountStatus {
  exists: boolean
  email: string | null
  created_at: string | null
}

type OS = 'macos' | 'linux' | 'windows'

function detectOS(): OS {
  const platform = navigator.platform.toLowerCase()
  if (platform.includes('mac')) return 'macos'
  if (platform.includes('win')) return 'windows'
  return 'linux'
}

function App() {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [magicToken, setMagicToken] = useState<MagicToken | null>(null)
  const [saStatus, setSaStatus] = useState<ServiceAccountStatus | null>(null)
  const [selectedOS, setSelectedOS] = useState<OS>(detectOS())
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchUser()
  }, [])

  const fetchUser = async () => {
    try {
      const res = await fetch('/api/auth/me', { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        setUser(data)
        fetchSAStatus()
      }
    } catch (err) {
      console.error('Failed to fetch user:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchSAStatus = async () => {
    try {
      const res = await fetch('/api/service-account/status', { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        setSaStatus(data)
      }
    } catch (err) {
      console.error('Failed to fetch SA status:', err)
    }
  }

  const handleLogin = () => {
    window.location.href = '/api/auth/google'
  }

  const handleLogout = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
      setUser(null)
      setMagicToken(null)
      setSaStatus(null)
    } catch (err) {
      console.error('Failed to logout:', err)
    }
  }

  const handleSetupEA = async () => {
    setError(null)
    try {
      const res = await fetch('/api/service-account/init', {
        method: 'POST',
        credentials: 'include',
      })
      if (res.ok) {
        const data = await res.json()
        setMagicToken(data)
      } else {
        const err = await res.json()
        setError(err.detail || 'Failed to initialize setup')
      }
    } catch (err) {
      setError('Failed to connect to server')
    }
  }

  const getCommand = () => {
    if (!magicToken) return ''
    switch (selectedOS) {
      case 'macos':
        return magicToken.command_macos
      case 'linux':
        return magicToken.command_linux
      case 'windows':
        return magicToken.command_windows
    }
  }

  const copyToClipboard = async () => {
    const command = getCommand()
    await navigator.clipboard.writeText(command)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-600">Loading...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-lg">F</span>
            </div>
            <h1 className="text-xl font-semibold text-gray-900">Fabric</h1>
          </div>
          {user && (
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                {user.picture && (
                  <img src={user.picture} alt="" className="w-8 h-8 rounded-full" />
                )}
                <span className="text-sm text-gray-700">{user.name}</span>
              </div>
              <button
                onClick={handleLogout}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-12">
        {!user ? (
          /* Login Section */
          <div className="text-center">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Your AI Executive Assistant
            </h2>
            <p className="text-lg text-gray-600 mb-8 max-w-2xl mx-auto">
              Set up your personal AI Executive Assistant to help you work with Google Docs and Sheets from the command line.
            </p>
            <button
              onClick={handleLogin}
              className="inline-flex items-center gap-2 bg-white border border-gray-300 rounded-lg px-6 py-3 text-gray-700 font-medium hover:bg-gray-50 shadow-sm"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              Sign in with Google
            </button>

            {/* How It Works */}
            <div className="mt-16 text-left">
              <h3 className="text-xl font-semibold text-gray-900 mb-6 text-center">
                How It Works
              </h3>
              <div className="grid md:grid-cols-3 gap-6">
                <div className="bg-white p-6 rounded-lg shadow-sm">
                  <div className="w-10 h-10 bg-indigo-100 rounded-full flex items-center justify-center mb-4">
                    <span className="text-indigo-600 font-bold">1</span>
                  </div>
                  <h4 className="font-medium text-gray-900 mb-2">Sign In</h4>
                  <p className="text-sm text-gray-600">
                    Log in with your Google Workspace account to get started.
                  </p>
                </div>
                <div className="bg-white p-6 rounded-lg shadow-sm">
                  <div className="w-10 h-10 bg-indigo-100 rounded-full flex items-center justify-center mb-4">
                    <span className="text-indigo-600 font-bold">2</span>
                  </div>
                  <h4 className="font-medium text-gray-900 mb-2">Run Setup Command</h4>
                  <p className="text-sm text-gray-600">
                    Copy and run the command in your terminal to configure your EA.
                  </p>
                </div>
                <div className="bg-white p-6 rounded-lg shadow-sm">
                  <div className="w-10 h-10 bg-indigo-100 rounded-full flex items-center justify-center mb-4">
                    <span className="text-indigo-600 font-bold">3</span>
                  </div>
                  <h4 className="font-medium text-gray-900 mb-2">Share Documents</h4>
                  <p className="text-sm text-gray-600">
                    Share docs/sheets with your EA's email to grant access.
                  </p>
                </div>
              </div>
            </div>

            {/* FAQ */}
            <div className="mt-16 text-left">
              <h3 className="text-xl font-semibold text-gray-900 mb-6 text-center">
                Frequently Asked Questions
              </h3>
              <div className="space-y-4">
                <details className="bg-white p-4 rounded-lg shadow-sm">
                  <summary className="font-medium text-gray-900 cursor-pointer">
                    What is an AI Executive Assistant?
                  </summary>
                  <p className="mt-2 text-sm text-gray-600">
                    Your AI Executive Assistant (EA) is a service account that can read and edit Google Docs and Sheets on your behalf. It has no access by default - you control exactly which documents it can access by sharing them.
                  </p>
                </details>
                <details className="bg-white p-4 rounded-lg shadow-sm">
                  <summary className="font-medium text-gray-900 cursor-pointer">
                    Is my data secure?
                  </summary>
                  <p className="mt-2 text-sm text-gray-600">
                    Yes. Your EA's credentials are stored only on your local machine. The portal never stores your private keys. You can revoke access to any document at any time by unsharing it.
                  </p>
                </details>
                <details className="bg-white p-4 rounded-lg shadow-sm">
                  <summary className="font-medium text-gray-900 cursor-pointer">
                    How do I use the EA with CLI tools?
                  </summary>
                  <p className="mt-2 text-sm text-gray-600">
                    Once set up, you can use the <code className="bg-gray-100 px-1 rounded">gdocs</code> and <code className="bg-gray-100 px-1 rounded">gsheets</code> command-line tools to interact with shared documents. These tools will automatically use your EA's credentials.
                  </p>
                </details>
                <details className="bg-white p-4 rounded-lg shadow-sm">
                  <summary className="font-medium text-gray-900 cursor-pointer">
                    Can I regenerate my EA's credentials?
                  </summary>
                  <p className="mt-2 text-sm text-gray-600">
                    Yes. Simply run the setup process again and new credentials will be generated. The old credentials will continue to work until you manually delete them.
                  </p>
                </details>
              </div>
            </div>
          </div>
        ) : (
          /* Dashboard Section */
          <div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              Welcome, {user.name.split(' ')[0]}!
            </h2>
            <p className="text-gray-600 mb-8">
              Set up your AI Executive Assistant to start working with Google Docs and Sheets.
            </p>

            {/* SA Status Card */}
            {saStatus?.exists && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-8">
                <div className="flex items-center gap-2 text-green-800">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span className="font-medium">Your EA is set up!</span>
                </div>
                <p className="mt-2 text-sm text-green-700">
                  EA Email: <code className="bg-green-100 px-2 py-0.5 rounded">{saStatus.email}</code>
                </p>
                <p className="mt-1 text-sm text-green-700">
                  Share documents with this email address to grant access.
                </p>
              </div>
            )}

            {/* Setup Section */}
            {!magicToken ? (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                  {saStatus?.exists ? 'Regenerate Credentials' : 'Set Up Your EA'}
                </h3>
                <p className="text-gray-600 mb-6">
                  {saStatus?.exists
                    ? 'Generate new credentials for your EA. Your current credentials will remain valid.'
                    : 'Click the button below to generate your EA credentials. You\'ll then run a command in your terminal to complete the setup.'}
                </p>
                {error && (
                  <div className="bg-red-50 text-red-700 p-3 rounded mb-4">
                    {error}
                  </div>
                )}
                <button
                  onClick={handleSetupEA}
                  className="bg-indigo-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-indigo-700"
                >
                  {saStatus?.exists ? 'Regenerate Credentials' : 'Set Up EA'}
                </button>
              </div>
            ) : (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                  Run This Command in Your Terminal
                </h3>

                {/* OS Selector */}
                <div className="flex gap-2 mb-4">
                  {(['macos', 'linux', 'windows'] as OS[]).map((os) => (
                    <button
                      key={os}
                      onClick={() => setSelectedOS(os)}
                      className={`px-4 py-2 rounded-lg text-sm font-medium ${
                        selectedOS === os
                          ? 'bg-indigo-600 text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {os === 'macos' ? 'macOS' : os === 'linux' ? 'Linux' : 'Windows'}
                    </button>
                  ))}
                </div>

                {/* Command Block */}
                <div className="relative">
                  <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
                    {getCommand()}
                  </pre>
                  <button
                    onClick={copyToClipboard}
                    className="absolute top-2 right-2 bg-gray-700 text-gray-200 px-3 py-1 rounded text-sm hover:bg-gray-600"
                  >
                    {copied ? 'Copied!' : 'Copy'}
                  </button>
                </div>

                <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                  <p className="text-sm text-amber-800">
                    <strong>Note:</strong> This command expires in 5 minutes. After running it, your EA email will be displayed. Make sure to note it down!
                  </p>
                </div>
              </div>
            )}

            {/* Instructions */}
            <div className="mt-8 bg-white rounded-lg shadow-sm p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                After Setup: How to Use Your EA
              </h3>
              <ol className="list-decimal list-inside space-y-3 text-gray-600">
                <li>
                  <strong>Share documents:</strong> Share any Google Doc or Sheet with your EA's email address.
                </li>
                <li>
                  <strong>Use CLI tools:</strong> Use <code className="bg-gray-100 px-1 rounded">gdocs</code> or <code className="bg-gray-100 px-1 rounded">gsheets</code> to read/edit shared documents.
                </li>
                <li>
                  <strong>Revoke access:</strong> Unshare a document to immediately revoke your EA's access.
                </li>
              </ol>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 mt-16">
        <div className="max-w-4xl mx-auto px-4 py-8">
          <p className="text-center text-sm text-gray-500">
            Fabric - Think41 Technologies
          </p>
        </div>
      </footer>
    </div>
  )
}

export default App

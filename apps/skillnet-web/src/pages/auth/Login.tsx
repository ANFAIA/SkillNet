import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Input } from '../../components/ui'
import { useLogin } from '../../api/auth'
import { useAuth } from '../../hooks/useAuth'
import { ApiError } from '../../api/client'

const HOME_BY_ROLE = {
  admin: '/admin',
  employee: '/empleado',
} as const

export function Login() {
  const navigate = useNavigate()
  const login = useLogin()
  const { user } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // If already authenticated, skip the form.
  useEffect(() => {
    if (user) navigate(HOME_BY_ROLE[user.role], { replace: true })
  }, [user, navigate])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!email.trim() || !password || login.isPending) return
    login.mutate(
      { email: email.trim(), password },
      {
        onSuccess: (loggedIn) => {
          navigate(HOME_BY_ROLE[loggedIn.role], { replace: true })
        },
      },
    )
  }

  const errorMessage =
    login.error instanceof ApiError
      ? login.error.status === 400 || login.error.status === 401
        ? 'Correo o contraseña incorrectos'
        : login.error.body.detail
      : login.error
        ? 'No se pudo iniciar sesion. Intentalo de nuevo.'
        : null

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="w-full max-w-sm bg-bg">
        <div className="flex flex-col items-center mb-6">
          <img src="/logo.png" alt="SkillNet" className="w-12 h-12 drop-shadow" />
          <h1 className="text-lg font-semibold text-text mt-3">SkillNet</h1>
          <p className="text-sm text-text-secondary mt-0.5">Inicia sesion para continuar</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Correo electronico"
            type="email"
            autoComplete="email"
            placeholder="tucorreo@empresa.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={login.isPending}
          />
          <Input
            label="Contraseña"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={login.isPending}
          />

          {errorMessage && <p className="text-sm text-danger">{errorMessage}</p>}

          <Button
            type="submit"
            size="lg"
            className="w-full"
            disabled={login.isPending || !email.trim() || !password}
          >
            {login.isPending ? 'Entrando...' : 'Entrar'}
          </Button>
        </form>
      </Card>
    </div>
  )
}

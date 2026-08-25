"""La ventana de `POST /setup` se cierra, y solo la reabre quien ve los logs.

`POST /setup` es publica por necesidad: es como se crea la primera cuenta, asi que no hay
nadie contra quien autenticar. Mientras un despliegue no tiene propietario, quien llegue
primero se convierte en su dueno. Inofensivo en localhost; no inofensivo en cuanto hay un
tunel o un proxy delante, que es facil de arrancar ANTES de crear la cuenta.
"""

import time

from src.core.setup_window import SetupWindow


def test_a_fresh_window_is_open():
    w = SetupWindow()
    w.open(30)
    assert w.is_open(30)


def test_a_window_that_was_never_opened_is_closed():
    """Si el arranque encontro un propietario, la ventana no se abre en absoluto."""
    assert not SetupWindow().is_open(30)


def test_the_window_closes_when_the_time_is_up():
    w = SetupWindow()
    w.open(30)
    # `opened_at` usa un reloj monotono: retrasarlo equivale a que pase el tiempo.
    w.opened_at = time.monotonic() - 31 * 60
    assert not w.is_open(30)


def test_zero_minutes_means_no_limit():
    """Valvula de escape para flujos automatizados, y avisada en el log."""
    w = SetupWindow()
    w.open(0)
    w.opened_at = time.monotonic() - 10_000
    assert w.is_open(0)


def test_the_token_reopens_a_closed_window():
    w = SetupWindow()
    w.open(30)
    assert w.token_matches(w.token)


def test_a_wrong_or_absent_token_never_matches():
    w = SetupWindow()
    w.open(30)
    for bad in (None, "", "otra-cosa", w.token[:-1]):
        assert not w.token_matches(bad)


def test_no_token_on_either_side_is_not_a_match():
    """Sin esto, una ventana sin abrir aceptaria una peticion sin cabecera."""
    assert not SetupWindow().token_matches(None)
    assert not SetupWindow().token_matches("cualquier-cosa")


def test_each_window_gets_its_own_token():
    a, b = SetupWindow(), SetupWindow()
    a.open(30)
    b.open(30)
    assert a.token != b.token
    assert not a.token_matches(b.token)

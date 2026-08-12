"""
Consulta DNI (RENIEC) / RUC (SUNAT) vía proveedores externos.

Configura en .env:
  CONSULTA_DOCUMENTO_TOKEN=tu_token
  CONSULTA_DOCUMENTO_PROVIDER=apis_net   # apis_net | decolecta

Si no hay token o el servicio falla, el cliente debe llenar los campos a mano.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class ResultadoConsulta:
    ok: bool
    numero: str
    tipo: str  # dni | ruc
    nombre: str = ''
    direccion: str = ''
    estado: str = ''
    fuente: str = ''
    mensaje: str = ''
    manual: bool = False

    def as_dict(self):
        return {
            'ok': self.ok,
            'numero': self.numero,
            'tipo': self.tipo,
            'nombre': self.nombre,
            'direccion': self.direccion,
            'estado': self.estado,
            'fuente': self.fuente,
            'mensaje': self.mensaje,
            'manual': self.manual,
        }


def _tipo_documento(numero: str) -> str | None:
    n = ''.join(c for c in (numero or '') if c.isdigit())
    if len(n) == 8:
        return 'dni'
    if len(n) == 11:
        return 'ruc'
    return None


def _http_get_json(url: str, headers: dict, timeout: int = 8) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8')
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode('utf-8')
            data = json.loads(body) if body else {}
        except Exception:
            data = {}
        return exc.code, data


def _desde_crm(numero: str) -> ResultadoConsulta | None:
    from apps.clientes.models import Cliente

    cli = Cliente.objects.filter(dni_ruc=numero).first()
    if not cli:
        return None
    return ResultadoConsulta(
        ok=True,
        numero=numero,
        tipo='ruc' if len(numero) == 11 else 'dni',
        nombre=cli.nombre_completo or '',
        direccion=cli.direccion or '',
        fuente='crm',
        mensaje='Cliente encontrado en el sistema',
    )


def _apis_net(numero: str, tipo: str, token: str) -> ResultadoConsulta:
    base = 'https://api.apis.net.pe/v2'
    path = f'/reniec/dni?numero={numero}' if tipo == 'dni' else f'/sunat/ruc?numero={numero}'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    status, data = _http_get_json(f'{base}{path}', headers)
    if status == 404:
        return ResultadoConsulta(
            ok=False, numero=numero, tipo=tipo, manual=True,
            mensaje='No se encontró el documento',
        )
    if status >= 400:
        raise RuntimeError(f'apis.net HTTP {status}')
    if tipo == 'dni':
        nombres = (data.get('nombres') or '').strip()
        ap_pat = (data.get('apellidoPaterno') or data.get('apellido_paterno') or '').strip()
        ap_mat = (data.get('apellidoMaterno') or data.get('apellido_materno') or '').strip()
        nombre = ' '.join(p for p in [nombres, ap_pat, ap_mat] if p).strip()
        if not nombre:
            nombre = (data.get('nombreCompleto') or data.get('nombre') or '').strip()
        return ResultadoConsulta(
            ok=bool(nombre), numero=numero, tipo=tipo, nombre=nombre,
            direccion=(data.get('direccion') or '').strip(),
            fuente='apis_net', mensaje='Datos desde RENIEC' if nombre else 'Sin nombre',
            manual=not bool(nombre),
        )
    nombre = (data.get('razonSocial') or data.get('nombre') or '').strip()
    return ResultadoConsulta(
        ok=bool(nombre), numero=numero, tipo=tipo, nombre=nombre,
        direccion=(data.get('direccion') or data.get('domicilioFiscal') or '').strip(),
        estado=(data.get('estado') or '').strip(),
        fuente='apis_net', mensaje='Datos desde SUNAT' if nombre else 'Sin razón social',
        manual=not bool(nombre),
    )


def _decolecta(numero: str, tipo: str, token: str) -> ResultadoConsulta:
    base = 'https://api.decolecta.com/v1'
    path = f'/reniec/dni?numero={numero}' if tipo == 'dni' else f'/sunat/ruc?numero={numero}'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    status, data = _http_get_json(f'{base}{path}', headers)
    if status == 404:
        return ResultadoConsulta(
            ok=False, numero=numero, tipo=tipo, manual=True,
            mensaje='No se encontró el documento',
        )
    if status >= 400:
        raise RuntimeError(f'decolecta HTTP {status}')
    if tipo == 'dni':
        first = (data.get('first_name') or data.get('nombres') or '').strip()
        ap_pat = (data.get('first_last_name') or data.get('apellido_paterno') or '').strip()
        ap_mat = (data.get('second_last_name') or data.get('apellido_materno') or '').strip()
        nombre = ' '.join(p for p in [first, ap_pat, ap_mat] if p).strip()
        if not nombre:
            nombre = (data.get('full_name') or data.get('nombre_completo') or '').strip()
        return ResultadoConsulta(
            ok=bool(nombre), numero=numero, tipo=tipo, nombre=nombre,
            fuente='decolecta', mensaje='Datos desde RENIEC' if nombre else 'Sin nombre',
            manual=not bool(nombre),
        )
    nombre = (
        data.get('razon_social') or data.get('nombre_o_razon_social')
        or data.get('razonSocial') or ''
    ).strip()
    return ResultadoConsulta(
        ok=bool(nombre), numero=numero, tipo=tipo, nombre=nombre,
        direccion=(data.get('direccion') or data.get('domicilio_fiscal') or '').strip(),
        estado=(data.get('estado') or '').strip(),
        fuente='decolecta', mensaje='Datos desde SUNAT' if nombre else 'Sin razón social',
        manual=not bool(nombre),
    )


def consultar_documento(numero: str) -> ResultadoConsulta:
    """
    Busca primero en CRM local; luego en API externa si hay token.
    Si falla, retorna manual=True para llenar a mano.
    """
    n = ''.join(c for c in (numero or '') if c.isdigit())
    tipo = _tipo_documento(n)
    if not tipo:
        return ResultadoConsulta(
            ok=False, numero=n, tipo='', manual=True,
            mensaje='Ingresa un DNI (8 dígitos) o RUC (11 dígitos)',
        )

    local = _desde_crm(n)
    if local:
        return local

    token = (getattr(settings, 'CONSULTA_DOCUMENTO_TOKEN', '') or '').strip()
    provider = (getattr(settings, 'CONSULTA_DOCUMENTO_PROVIDER', 'apis_net') or 'apis_net').strip().lower()

    if not token:
        return ResultadoConsulta(
            ok=False, numero=n, tipo=tipo, manual=True,
            mensaje='Consulta externa no configurada. Completa el nombre manualmente.',
        )

    try:
        if provider == 'decolecta':
            return _decolecta(n, tipo, token)
        return _apis_net(n, tipo, token)
    except Exception as exc:
        logger.warning('Consulta documento falló (%s): %s', provider, exc)
        return ResultadoConsulta(
            ok=False, numero=n, tipo=tipo, manual=True,
            mensaje='No se pudo consultar el servicio. Completa los datos a mano.',
        )

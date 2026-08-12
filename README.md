# Charly Makita — Tienda + Servicio Técnico (Arequipa)

Plataforma Django para **Charly Makita**: tienda web de herramientas/accesorios Makita y sistema interno (POS, CRM, cotizaciones, servicio técnico 300h).

Zona horaria: `America/Lima` · Idioma: `es-pe` · Moneda: `S/`.

## Requisitos

- Docker y Docker Compose (recomendado), **o**
- Python 3.12 + PostgreSQL 15

## Arranque rápido (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- App: http://127.0.0.1:8090/
- Postgres: `localhost:5435` (usuario/clave en `docker-compose.yml`)

En desarrollo el servicio `web` usa `runserver`. Para Gunicorn:

```bash
docker compose --profile prod up --build web_prod
```

### Crear superusuario

```bash
docker compose exec web python manage.py createsuperuser
```

### Tests

```bash
docker compose exec web python manage.py test apps.tienda.tests apps.pedidos.tests apps.pagos.tests apps.mantenimiento.tests apps.usuarios.tests apps.pos.tests apps.clientes.tests apps.cotizaciones.tests apps.inventario.tests apps.reportes.tests --keepdb
```

> Si `SECRET_KEY` en `.env` contiene `$`, escápelo como `$$` para Docker Compose.

## Roles

| Rol | Acceso |
|-----|--------|
| `admin` | Admin Unfold + todos los módulos |
| `vendedor` | POS, pagos pendientes, pedidos, CRM, cotizaciones, reportes |
| `tecnico` | Mantenimiento / taller, CRM, cotizaciones, reportes |
| `cliente` | Tienda pública + **Mi cuenta** (pedidos y equipos) |

## URLs útiles

| Ruta | Descripción |
|------|-------------|
| `/catalogo/` | Catálogo público |
| `/tienda/carrito/` | Carrito de compras |
| `/tienda/checkout/` | Checkout y pago |
| `/registro/` | Alta de cliente |
| `/mi-cuenta/` | Historial pedidos / equipos |
| `/pagos/pendientes/` | Staff: aprobar Yape/Plin/transferencia |
| `/pedidos/staff/` | Staff: estados de pedido |
| `/pos/` | Punto de venta |
| `/mantenimiento/` | Servicio técnico |
| `/mi-pedido/` | Consulta de pedido (DNI + teléfono) |
| `/admin/` | Django Admin + Unfold |

## Pagos

- **Web:** Yape / Plin (con voucher) o **pagar en tienda** (reserva 24 h).
- **POS:** efectivo, Yape, Plin, tarjeta, transferencia o combinado (ticket interno).
- Pasarela Culqi **no está activa** por ahora.

## Estructura

```
apps/
  tienda/          Catálogo y carrito
  pedidos/         Checkout y gestión de pedidos
  pagos/           Aprobación de pagos manuales
  pos/             Caja y tickets
  mantenimiento/   Taller y equipos 300h
  clientes/        CRM
  cotizaciones/    Cotizaciones PDF
  inventario/      Movimientos de stock
  reportes/        Dashboard KPIs
  usuarios/        Auth y área cliente
```

Roadmap de producto: [`plan_charly_makita.md`](plan_charly_makita.md).

## Internet en tienda (failover 4G)

El sistema es **web** (navegador → servidor). No hace falta un ejecutable Windows.

1. Router con **failover 4G** (chip Claro/Movistar/Entel) o hotspot de respaldo: si cae el WiFi/fibra, el router cambia solo.
2. El POS reintenta búsquedas y cobra con clave anti-duplicado ante cortes de pocos segundos.
3. Monitoriza el servidor: `http://TU-SERVIDOR:8090/health/` debe responder `{"ok": true, "db": "ok"}`.

Si los cortes duran **minutos u horas** y no puedes vender, ahí sí conviene un PC local con Docker (mismo proyecto). Con solo intermitencias, web + 4G basta.

## Notas

- Los equipos vendidos (familia EQUIPOS / tipo herramienta) se registran automáticamente para el mantenimiento gratuito a las **300 horas**.
- Web y POS comparten inventario, con stock **tienda** y **web** (el POS puede usar stock web automáticamente).

## Despliegue en dominio

1. Copia `.env.example` → `.env` y configura producción:
   - `DEBUG=False`
   - `SECRET_KEY` fuerte y único (sin `django-insecure-`)
   - `ALLOWED_HOSTS=tudominio.pe,www.tudominio.pe`
   - `CSRF_TRUSTED_ORIGINS=https://tudominio.pe,https://www.tudominio.pe`
   - Con HTTPS estable: `SECURE_SSL_REDIRECT=True` y `ENABLE_HSTS=True`
   - SMTP real (`EMAIL_*`)
2. Arranque:
   - Desarrollo: `docker compose up -d --build`
   - Producción: `docker compose --profile prod up -d --build db web_prod`
3. Crea superusuario y publica productos en **Productos web**.
4. Pon un reverse proxy (nginx/Caddy) con HTTPS hacia el puerto `8090`.
5. Sube el QR de Yape a `media/yape-qr.png` si lo usan en checkout.
6. Agenda (cron) la liberación de reservas web expiradas:
   ```bash
   docker compose exec web_prod python manage.py liberar_pedidos_expirados
   ```

Pendiente de negocio (no bloquea el deploy básico): emisión electrónica de boleta/factura SUNAT, delivery a domicilio, pasarela de tarjeta (Culqi/Izipay) si la habilitan después.

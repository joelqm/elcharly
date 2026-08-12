# Plan de Proyecto: Plataforma Web Charly Makita — Arequipa

**Servicio Técnico Autorizado Makita | Tienda Virtual + CRM + POS + Mantenimiento**

---

## Stack Tecnológico

| Componente | Tecnología |
|---|---|
| Backend | Django 5 (Python) |
| Base de datos | PostgreSQL |
| Panel de administración | Django Admin + Unfold (estilos modernos) |
| Frontend público | HTML + JavaScript Vanilla + Django Templates |
| Servidor de producción | Nginx + Gunicorn en VPS (DigitalOcean o similar) |
| Pagos | Culqi o Izipay (pasarelas peruanas) |
| Correos transaccionales | SendGrid o SMTP propio |
| Almacenamiento de imágenes | AWS S3 o Cloudflare R2 |
| Impresión de tickets | ESC/POS (impresora térmica) vía JavaScript |

---

## Estructura de Aplicaciones Django

El proyecto se divide en aplicaciones (apps) independientes dentro de Django:

```
proyecto_makita/
├── apps/
│   ├── tienda/          → Catálogo de productos, categorías, búsqueda
│   ├── pedidos/         → Órdenes web y ventas en tienda física
│   ├── clientes/        → CRM: registro, historial, seguimiento
│   ├── mantenimiento/   → Registro de equipos, contador de horas, alertas
│   ├── cotizaciones/    → Cotización de repuestos, generación de PDF
│   ├── inventario/      → Stock, alertas de bajo inventario
│   ├── pagos/           → Integración con pasarela de pagos
│   ├── pos/             → Punto de venta físico, caja, tickets
│   └── reportes/        → Dashboard, exportaciones, estadísticas
├── templates/           → Plantillas HTML
├── static/              → CSS, JS, imágenes del sistema
└── media/               → Imágenes subidas por el administrador
```

---

## Base de Datos — Modelos Principales

### Producto
```
- id
- nombre
- descripcion
- categoria (FK → Categoria)
- marca (siempre Makita)
- modelo (ej: DHP484Z)
- tipo (herramienta / accesorio / repuesto)
- precio_venta
- precio_costo
- stock
- imagen_principal
- peso
- voltaje
- activo (booleano)
- fecha_creacion
```

### Categoria
```
- id
- nombre (ej: Taladros, Esmeriles, Discos, Brocas)
- categoria_padre (FK a sí mismo, para subcategorías)
- imagen
```

### Cliente
```
- id
- nombre_completo
- tipo (persona natural / empresa)
- dni o ruc
- telefono
- correo
- direccion
- ciudad
- fecha_registro
- canal_origen (web / tienda física / referido)
- notas
```

### Pedido
```
- id
- numero_pedido (correlativo, ej: ORD-2024-0001)
- cliente (FK → Cliente)
- canal (web / pos / cotizacion)
- estado (pendiente / pagado / enviado / entregado / cancelado)
- fecha_pedido
- subtotal
- igv (18%)
- total
- direccion_envio
- notas
- atendido_por (FK → Usuario)
```

### DetallePedido
```
- id
- pedido (FK → Pedido)
- producto (FK → Producto)
- cantidad
- precio_unitario
- subtotal
```

### Pago
```
- id
- pedido (FK → Pedido)
- metodo (efectivo / yape / plin / tarjeta / transferencia)
- monto
- estado (pendiente / aprobado / rechazado / reembolsado)
- referencia_externa (código de la pasarela)
- fecha_pago
```

### EquipoRegistrado
```
- id
- cliente (FK → Cliente)
- pedido_origen (FK → Pedido)
- producto (FK → Producto)
- numero_serie
- fecha_compra
- horas_uso_actuales
- horas_proximo_mantenimiento (por defecto: 300)
- estado (activo / en_mantenimiento / dado_de_baja)
- garantia_hasta (fecha)
```

### Mantenimiento
```
- id
- equipo (FK → EquipoRegistrado)
- tipo (preventivo_300h / correctivo / garantia)
- fecha_ingreso
- fecha_entrega_estimada
- fecha_entrega_real
- tecnico (FK → Usuario)
- diagnostico
- trabajos_realizados
- repuestos_usados (ManyToMany → Producto)
- costo_mano_obra
- costo_repuestos
- total
- estado (ingresado / en_proceso / listo / entregado)
- observaciones
```

### Cotizacion
```
- id
- numero (correlativo, ej: COT-2024-0001)
- cliente (FK → Cliente, puede ser nulo si es anónimo)
- modelo_equipo (texto libre: ej. "Taladro Makita HP2070")
- estado (borrador / enviada / aprobada / rechazada)
- fecha_creacion
- fecha_vencimiento
- subtotal
- igv
- total
- notas
```

### DetalleCotizacion
```
- id
- cotizacion (FK → Cotizacion)
- repuesto (FK → Producto)
- descripcion_manual (si no está en el catálogo)
- cantidad
- precio_unitario
- subtotal
```

### TicketPOS
```
- id
- numero_serie (ej: T-2024-00123)
- pedido (FK → Pedido)
- cajero (FK → Usuario)
- fecha_emision
- subtotal
- igv
- total
- tipo_comprobante (boleta / factura / ticket simple)
- ruc_cliente (para facturas)
- impreso (booleano)
```

---

## Etapas de Construcción

---

### ETAPA 1 — Base del Proyecto y Autenticación
**Duración estimada: 2 semanas**

**Objetivo:** Tener el proyecto Django funcionando con estructura correcta, base de datos conectada y sistema de usuarios.

**Tareas:**

1. Crear el proyecto Django con la estructura de carpetas definida arriba
2. Configurar PostgreSQL como base de datos
3. Instalar y configurar Unfold para el panel de administración
4. Crear el modelo de Usuarios con roles:
   - Administrador (acceso total)
   - Vendedor (tienda y POS)
   - Técnico (mantenimiento)
   - Cliente (solo tienda pública)
5. Implementar login, logout, recuperación de contraseña
6. Configurar variables de entorno con `python-decouple` o `django-environ`
7. Configurar almacenamiento de imágenes (local en desarrollo, S3 en producción)
8. Crear el archivo `requirements.txt` con todas las dependencias
9. Configurar el servidor de correo para notificaciones básicas

**Resultado de esta etapa:** El proyecto corre localmente, el panel de admin funciona con Unfold, los usuarios pueden iniciar sesión con su rol correspondiente.

---

### ETAPA 2 — Catálogo de Productos, Categorías e Inventario
**Duración estimada: 3 semanas**

**Objetivo:** Tener toda la tienda virtual con catálogo navegable y gestión de stock.

**Tareas:**

1. Crear los modelos: `Categoria`, `Producto`
2. Panel de admin para cargar y editar productos con imágenes
3. Página pública de tienda con:
   - Lista de productos con filtros (categoría, precio, tipo)
   - Página de detalle de producto con galería de imágenes
   - Buscador por nombre y modelo
4. Módulo de inventario:
   - Ver stock actual por producto
   - Alertas cuando el stock baja de un mínimo definido
   - Historial de movimientos (entradas y salidas)
5. Importación masiva de productos desde Excel (opcional pero recomendado)
6. SEO básico: URL amigables, meta tags por producto

**Resultado de esta etapa:** La tienda pública está visible, los productos se pueden navegar y filtrar, el inventario se gestiona desde el admin.

---

### ETAPA 3 — Pedidos Web, Carrito y Pagos en Línea
**Duración estimada: 3 semanas**

**Objetivo:** Los clientes pueden comprar desde la web pagando con Culqi o Izipay.

**Tareas:**

1. Crear el carrito de compras (usando sesiones de Django o base de datos)
2. Flujo de checkout:
   - Resumen del carrito
   - Datos de entrega
   - Selección de método de pago
   - Confirmación del pedido
3. Integración con pasarela de pagos (Culqi recomendado para Perú):
   - Pago con tarjeta débito/crédito
   - Webhook para confirmar pagos automáticamente
4. Envío de correo de confirmación al cliente después del pago
5. Panel de admin para ver y gestionar todos los pedidos web
6. Cambio de estado de pedidos (pendiente → pagado → enviado → entregado)
7. Historial de compras del cliente en su perfil

**Resultado de esta etapa:** Un cliente puede entrar a la web, agregar productos al carrito, pagar con tarjeta y recibir su confirmación por correo.

---

### ETAPA 4 — Punto de Venta (POS) para Tienda Física
**Duración estimada: 2 semanas**

**Objetivo:** El vendedor en tienda puede registrar ventas, cobrar y emitir tickets.

**Tareas:**

1. Pantalla de POS (interfaz rápida y simple para el vendedor):
   - Buscar producto por nombre o escanear código
   - Agregar productos a la venta actual
   - Aplicar descuentos
   - Registrar el método de pago (efectivo, Yape, Plin, tarjeta)
2. Generación del ticket de venta:
   - Número de serie correlativo
   - Detalle de productos comprados
   - Total con IGV desglosado
   - Datos del negocio (RUC, dirección, etc.)
3. Impresión en impresora térmica via ESC/POS desde el navegador
4. Cierre de caja diario:
   - Resumen de ventas del día
   - Total por método de pago
   - Exportar resumen del día
5. Soporte para boletas y facturas

**Resultado de esta etapa:** El vendedor en tienda puede atender a un cliente en menos de 2 minutos, registrar la venta e imprimir el ticket.

---

### ETAPA 5 — Registro de Equipos y Módulo de Mantenimiento
**Duración estimada: 2 semanas**

**Objetivo:** Registrar automáticamente cada equipo vendido y gestionar el mantenimiento de 300 horas.

**Tareas:**

1. Al confirmar una venta (web o POS), registrar automáticamente el equipo en `EquipoRegistrado`
2. Formulario para ingresar el número de serie del equipo al momento de la venta
3. Panel del técnico:
   - Ver todos los equipos registrados de un cliente
   - Registrar un nuevo ingreso de equipo para mantenimiento
   - Actualizar las horas de uso actuales
4. Lógica del contador de 300 horas:
   - Cuando `horas_uso_actuales` supera las `horas_proximo_mantenimiento`, el equipo aparece con alerta
   - Al completar un mantenimiento, reiniciar el contador y programar el siguiente
5. Notificaciones automáticas:
   - Correo al cliente cuando su equipo está listo para retirarse
   - Alerta al técnico cuando hay equipos pendientes de hace más de X días
6. Historial completo de cada equipo: cuántos mantenimientos tuvo, qué repuestos se usaron, qué técnico lo atendió

**Resultado de esta etapa:** Cada equipo vendido tiene su ficha técnica, el sistema avisa cuando necesita mantenimiento y el cliente puede ver el historial de su equipo.

---

### ETAPA 6 — CRM, Cotizaciones y Reportes
**Duración estimada: 2 semanas**

**Objetivo:** Tener una vista completa de clientes, ventas y cotizaciones de repuestos.

**Tareas:**

1. Módulo CRM de clientes:
   - Ficha completa del cliente con historial de compras y mantenimientos
   - Búsqueda rápida por nombre, DNI, RUC o teléfono
   - Etiquetas para clasificar clientes (frecuente, empresa, nuevo, etc.)
   - Notas internas sobre el cliente
2. Módulo de cotizaciones de repuestos:
   - Crear cotización para un cliente o de forma anónima
   - Buscar repuestos del catálogo o agregarlos manualmente
   - Generar PDF de la cotización para enviar al cliente
   - Registrar si la cotización fue aprobada (convierte en pedido)
3. Dashboard de reportes:
   - Ventas del día / semana / mes
   - Productos más vendidos
   - Equipos pendientes de mantenimiento
   - Cotizaciones pendientes de respuesta
4. Exportación de reportes a Excel

**Resultado de esta etapa:** El administrador tiene visibilidad total del negocio desde una sola pantalla.

---

### ETAPA 7 — Pruebas, Deploy y Capacitación
**Duración estimada: 2 semanas**

**Objetivo:** El sistema está en producción, funciona correctamente y el equipo sabe usarlo.

**Tareas:**

1. Pruebas de funcionalidad completa (cada módulo)
2. Pruebas de seguridad básicas (SQL injection, CSRF, acceso por roles)
3. Configuración del servidor de producción:
   - VPS con Ubuntu (DigitalOcean, Contabo, o similar)
   - Nginx como servidor web
   - Gunicorn como servidor WSGI
   - Certificado SSL (HTTPS gratuito con Let's Encrypt)
   - Dominio propio
4. Configuración de backups automáticos de la base de datos
5. Manual de usuario básico (cómo cargar productos, cómo procesar ventas, cómo registrar mantenimientos)
6. Sesión de capacitación con el equipo

**Resultado de esta etapa:** La plataforma está en línea, segura y el equipo sabe operarla.

---

## Resumen de Tiempos

| Etapa | Descripción | Duración |
|---|---|---|
| 1 | Base del proyecto y autenticación | 2 semanas |
| 2 | Catálogo, tienda e inventario | 3 semanas |
| 3 | Pedidos web, carrito y pagos | 3 semanas |
| 4 | POS para tienda física | 2 semanas |
| 5 | Registro de equipos y mantenimiento | 2 semanas |
| 6 | CRM, cotizaciones y reportes | 2 semanas |
| 7 | Pruebas, deploy y capacitación | 2 semanas |
| **Total** | | **16 semanas aprox.** |

---

## Dependencias Python Principales

```
django>=5.0
psycopg2-binary          # Conector PostgreSQL
django-unfold            # Estilos modernos para el admin
pillow                   # Manejo de imágenes
django-environ           # Variables de entorno
django-crispy-forms      # Formularios con estilo
reportlab o weasyprint   # Generación de PDFs (cotizaciones, tickets)
openpyxl                 # Exportación a Excel
requests                 # Llamadas a APIs externas (pasarela de pagos)
gunicorn                 # Servidor WSGI para producción
whitenoise               # Servir archivos estáticos en producción
```

---

## Notas Importantes

- **Todos los equipos vendidos incluyen mantenimiento gratuito a las 300 horas.** Este dato debe registrarse en `EquipoRegistrado` y el sistema debe avisar automáticamente cuando se acerque ese límite.
- **La plataforma maneja dos canales de venta:** web (clientes desde internet) y POS (clientes en tienda física). Ambos canales comparten el mismo inventario.
- **Solo se vende la marca Makita.** El campo marca en el modelo Producto puede dejarse fijo como "Makita" o usarse para repuestos compatibles.
- **El módulo de cotizaciones** está pensado principalmente para repuestos, que los clientes consultan antes de decidir si reparar o comprar nuevo.
- **Charly Makita es el servicio técnico autorizado en Arequipa**, por lo que el historial de mantenimiento es un diferencial importante del negocio y debe ser fácil de consultar por el equipo técnico.

---

*Documento generado para: Charly Makita — Servicio Técnico Autorizado Makita, Arequipa, Perú*

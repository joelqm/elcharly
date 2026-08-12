---
name: django_best_practices
description: Best practices for building Django + Docker + PostgreSQL web applications, focusing on architectural design, code style, and developer efficiency.
---

# Django & Docker Best Practices for Makita Platform

Guidelines and standards to be followed automatically during the development of this project.

## 1. Project Structure & Organization
- **Nested Apps**: All Django applications must reside inside the `apps/` directory.
  - Structure: `proyecto_makita/apps/tienda/`
  - In `apps/tienda/apps.py`, set the `name` to `'apps.tienda'` and define the label if necessary.
  - In `settings.py`, include them as `'apps.tienda'`, etc.
- **Clean Configuration**:
  - Keep sensitive data (passwords, secret keys, API keys, database URLs) in a `.env` file.
  - Do not commit the `.env` file to Git. Provide a `.env.example` file instead.
  - Use `django-environ` to read and parse environment variables.

## 2. Docker & Database Standards
- Use a `docker-compose.yml` file to manage the PostgreSQL database and any other local service.
- The PostgreSQL data must be persisted via a Docker volume (e.g., `postgres_data`).
- Map PostgreSQL to a non-conflicting host port if `5432` is occupied.
- Database connections must use `django-environ` to parse the `DATABASE_URL`.

## 3. Django Models (Fat Models, Thin Views)
- **Custom User Model**: Always implement a custom user model inheriting from `AbstractUser` before the first migration.
- **ForeignKey Rules**:
  - Always specify `on_delete` behavior (e.g., `models.CASCADE`, `models.PROTECT`, `models.SET_NULL`).
  - Use `related_name` for reverse relations to avoid collision and keep queries clean.
- **Clean Architecture**:
  - Encapsulate business logic within model methods or helper services rather than views.
  - Keep views thin and focused on HTTP request-response handling.

## 4. UI/UX & Styling Guidelines
- **Rich Aesthetics**: The design must feel modern, clean, and professional.
- **Color Palette**: Use Makita's corporate colors (teal/turquoise `#008B8B`, dark gray/black `#222222`, white `#FFFFFF`) combined with modern UI design principles (soft borders, clean typography, subtle micro-animations).
- **Django Templates**:
  - Extend a base template (`base.html`) for header, footer, styles, and scripts.
  - Use semantic HTML5 elements.
  - Ensure fast load times and clean organization of static files (`/static/css/`, `/static/js/`).

## 5. Security & Performance
- **CSRF & XSS Protection**: Ensure `{% csrf_token %}` is used in all POST forms.
- **Database Optimization**:
  - Use `select_related` for one-to-many/one-to-one relations in queries.
  - Use `prefetch_related` for many-to-many/reverse relations.
  - Index fields that are frequently filtered or searched.
- **Security Check**:
  - Never run Django with `DEBUG=True` in a public production environment.
  - Set appropriate `ALLOWED_HOSTS`.

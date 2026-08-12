@echo off
setlocal
cd /d "%~dp0"

echo.
echo === El Charly · levantar con Docker (CMD) ===
echo.

where docker >nul 2>&1
if errorlevel 1 (
  echo [ERROR] No se encontro "docker" en el PATH.
  echo Instala Docker Desktop o agrega Docker al PATH.
  exit /b 1
)

echo Comprobando que el motor Docker este listo...
set /a n=0
:wait_docker
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
set /a n+=1
if %n% GEQ 40 (
  echo [ERROR] Docker Desktop no responde.
  echo Abre Docker Desktop, espera el icono verde/estable y vuelve a ejecutar up.cmd
  exit /b 1
)
echo   Esperando motor... (%n%/40)
timeout /t 5 /nobreak >nul
goto wait_docker

:docker_ok
echo Motor OK. Levantando db + web...
docker compose up -d db web
if errorlevel 1 (
  echo [ERROR] docker compose fallo.
  exit /b 1
)

echo Migraciones cotizaciones / pendientes...
docker compose exec -T web python manage.py migrate --noinput

echo.
echo Listo:
echo   Sistema POS : http://127.0.0.1:8090/pos/login/
echo   Web publica : http://127.0.0.1:8090/  (en construccion si WEB_PUBLICA_ACTIVA=False)
echo.
endlocal

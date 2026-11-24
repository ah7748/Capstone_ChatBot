"""Integración opcional con Azure Application Insights (OpenTelemetry).

Se activa solo si APPLICATIONINSIGHTS_CONNECTION_STRING está definida y el paquete
`azure-monitor-opentelemetry` está instalado (ver requirements-azure.txt). En cualquier otro
caso no hace nada, así que el despliegue sin Azure (Railway) no se ve afectado.
"""
import logging

logger = logging.getLogger("app.observability")


def setup_azure_monitor(connection_string: str) -> bool:
    """Devuelve True si la telemetría hacia Application Insights quedó activa."""
    if not connection_string:
        return False
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING está definida, pero falta el paquete "
                       "azure-monitor-opentelemetry (pip install -r requirements-azure.txt)")
        return False
    try:
        configure_azure_monitor(connection_string=connection_string)
    except Exception:
        logger.exception("No se pudo activar Application Insights; la app sigue sin esa telemetría")
        return False
    logger.info("Application Insights activado")
    return True

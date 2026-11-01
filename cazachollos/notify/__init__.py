"""Módulo de notificaciones. Importa send_alert para enviar por cualquier canal."""

from .telegram import TelegramNotifier

__all__ = ["TelegramNotifier"]

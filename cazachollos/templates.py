"""Plantillas de texto para comunicaciones con vendedores.

Genera el mensaje de WhatsApp/chat con las preguntas clave para cada anuncio.
"""

from __future__ import annotations

from .models import Listing

_BASE_QUESTIONS = [
    "¿Cuál es el motivo de la venta?",
    "¿Cuántos propietarios ha tenido?",
    "¿Tiene el libro de revisiones o historial de mantenimiento?",
    "¿Está al día la ITV?",
    "¿Tiene cargas (embargo, reserva de dominio)?",
    "¿Está libre de deudas (multas, impuestos municipales)?",
    "¿Se puede ver con un mecánico de confianza?",
]


def seller_message(lst: Listing, max_offer: float | None = None) -> str:
    """Genera el mensaje de contacto para WhatsApp o chat del portal.

    Incluye preguntas clave adaptadas al anuncio.
    """
    parts = [f"Hola, me interesa tu {lst.title or f'{lst.make} {lst.model}'}."]
    if lst.km:
        parts.append(f"Veo que tiene {lst.km:,} km, ¿son reales y verificables?".replace(",", "."))

    questions = list(_BASE_QUESTIONS)

    # Preguntas extra según el anuncio
    if lst.fuel == "diesel":
        questions.append("¿El FAP/DPF está en buen estado? ¿Aparece algún testigo encendido?")
    if lst.fuel in ("diesel",) and (lst.year or 0) < 2012:
        questions.append("¿Tiene la correa de distribución cambiada? ¿Cuándo fue la última revisión?")
    if lst.km and lst.km > 150000:
        questions.append("Con estos km, ¿se ha revisado la distribución, embrague o caja?")
    if lst.transmission == "automatico":
        questions.append("¿El cambio automático funciona con suavidad? ¿Se ha cambiado el aceite de caja?")
    if lst.year and (2024 - lst.year) >= 10:
        questions.append("¿Tiene algún golpe, óxido o problema de chapa que no salga en las fotos?")

    numbered = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    parts.append(f"\nAlgunas preguntas:\n{numbered}")

    if max_offer is not None:
        parts.append(
            f"\nSi todo está bien, podría llegar hasta {max_offer:,.0f} € al contado "
            "y me encargo del papeleo.".replace(",", ".")
        )
    parts.append("\n¿Cuándo podría verlo?")
    return "\n".join(parts)


def inspection_checklist(lst: Listing) -> list[str]:
    """Lista de puntos a revisar en la inspección física del coche."""
    items = [
        "Revisar número de bastidor (VIN) — coincide con el del permiso de circulación",
        "Comprobar km en el cuadro (pedir informe DGT si hay duda)",
        "Inspección de carrocería: golpes, óxido, diferencia de color entre paneles",
        "Revisar aletas y umbrales: óxido debajo indica coche costero o mal mantenido",
        "Abrir capó: nivel de aceite, refrigerante, signos de fuga o recalentamiento",
        "Arrancar en frío: humo azul (aceite), negro (combustible) o blanco (refrigerante)",
        "Probar todos los elevalunas, espejos, aire acondicionado, calefacción",
        "Testigos en el cuadro: ninguno debe estar encendido al arrancar (salvo ABS momentáneo)",
        "Prueba de carretera: frenos, dirección, cambio de marchas, aceleración",
        "Revisar neumáticos: desgaste uniforme (si no, puede indicar problemas de dirección)",
        "Revisar amortiguadores: rebotar cada esquina del coche",
        "Comprobar el maletero: presencia de rueda de repuesto y gato",
        "Verificar documentación: permiso de circulación, ITV, historial de revisiones",
    ]
    if lst.fuel == "diesel":
        items.append("Diesel: comprobar estado del FAP/DPF (testigo naranja), EGR")
    if lst.fuel in ("hibrido", "hibrido_enchufable", "electrico"):
        items.append("Eléctrico/Híbrido: pedir estado de la batería de alta tensión (%)")
    if (lst.km or 0) > 120000:
        items.append("Alta km: preguntar si se ha cambiado embrague, distribución y volante bimasa")
    return items

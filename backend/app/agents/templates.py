"""Standard replies, used when the writer fails or its draft fails the guard (design §7.2, R-12).

Same rules as the writer (design §7.1): greet by first name, plain words, no internal
terms, only the case's own facts, sign off as "<credit union> Member Support". The manual
template is a neutral start for Luis: it promises nothing.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from app.rules.fees import plain_name
from app.rules.model import FeeType, ReasonCode, Recommendation
from app.rules.texts import money

Language = Literal["en", "es"]
TemplateKey = Literal[
    "REFUND",
    "ALREADY_REFUNDED",
    "OUT_OF_WINDOW",
    "NOT_GOOD_STANDING",
    "NO_QUALIFYING_REASON",
    "LIMIT_REACHED",
    "MANUAL",
]

_MONTHS_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")  # fmt: skip
_FEE_NAMES_ES = {
    FeeType.COURTESY_PAY: "comisión por sobregiro",
    FeeType.NSF: "comisión por pago devuelto",
    FeeType.OUT_OF_NETWORK_ATM: "comisión por cajero fuera de la red",
    FeeType.EXCESS_WITHDRAWAL: "comisión por retiro de ahorros",
    FeeType.OTHER: "comisión",
}
_MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")  # fmt: skip

_TEMPLATES: dict[tuple[TemplateKey, Language], str] = {
    ("REFUND", "en"): "Hi {name},\n\nWe've refunded the {amount} {fee} from {day}. The money is back in your account today.\n\nThank you for reaching out.\n\n{signature}",
    ("REFUND", "es"): "Hola {name}:\n\nYa reembolsamos la {fee} de {amount} del {day}. El dinero está de nuevo en tu cuenta hoy.\n\nGracias por escribirnos.\n\n{signature}",
    ("ALREADY_REFUNDED", "en"): "Hi {name},\n\nThe {amount} {fee} from {day} was already refunded, so there's nothing more to refund. Is there anything else we can help you with?\n\n{signature}",
    ("ALREADY_REFUNDED", "es"): "Hola {name}:\n\nLa {fee} de {amount} del {day} ya fue reembolsada, así que no queda nada pendiente. ¿Te podemos ayudar con algo más?\n\n{signature}",
    ("OUT_OF_WINDOW", "en"): "Hi {name},\n\nWe can only refund a fee when we hear about it within {days} days, and the {amount} {fee} from {day} is older than that. Is there anything else we can help you with?\n\n{signature}",
    ("OUT_OF_WINDOW", "es"): "Hola {name}:\n\nSolo podemos reembolsar una comisión si nos escribes dentro de los {days} días siguientes, y la {fee} de {amount} del {day} es anterior. ¿Te podemos ayudar con algo más?\n\n{signature}",
    ("NOT_GOOD_STANDING", "en"): "Hi {name},\n\nWe're not able to refund the {amount} {fee} from {day} on your account at this time. Is there anything else we can help you with?\n\n{signature}",
    ("NOT_GOOD_STANDING", "es"): "Hola {name}:\n\nEn este momento no podemos reembolsar la {fee} de {amount} del {day} en tu cuenta. ¿Te podemos ayudar con algo más?\n\n{signature}",
    ("NO_QUALIFYING_REASON", "en"): "Hi {name},\n\nWe looked at {day}: no deposit arrived that day that would have covered the payment, so we can't refund the {amount} {fee}. Is there anything else we can help you with?\n\n{signature}",
    ("NO_QUALIFYING_REASON", "es"): "Hola {name}:\n\nRevisamos el {day}: ese día no llegó un depósito que cubriera el pago, así que no podemos reembolsar la {fee} de {amount}. ¿Te podemos ayudar con algo más?\n\n{signature}",
    ("LIMIT_REACHED", "en"): "Hi {name},\n\nYou've already used all the fee refunds available in the last 12 months, so we can't refund the {amount} {fee} from {day}. Is there anything else we can help you with?\n\n{signature}",
    ("LIMIT_REACHED", "es"): "Hola {name}:\n\nYa usaste todos los reembolsos de comisiones disponibles en los últimos 12 meses, así que no podemos reembolsar la {fee} de {amount} del {day}. ¿Te podemos ayudar con algo más?\n\n{signature}",
    ("MANUAL", "en"): "Hi {name},\n\nThank you for your message. We're looking into it and will get back to you soon.\n\n{signature}",
    ("MANUAL", "es"): "Hola {name}:\n\nGracias por tu mensaje. Lo estamos revisando y te responderemos pronto.\n\n{signature}",
}  # fmt: skip

_SIGNATURES = {
    "en": "{credit_union} Member Support",
    "es": "Equipo de atención al asociado de {credit_union}",
}


@dataclass(frozen=True)
class FeeFacts:
    fee_type: FeeType
    amount: Decimal
    day: date


def template_key(recommendation: Recommendation, reason: ReasonCode) -> TemplateKey:
    if recommendation is Recommendation.REFUND:
        return "REFUND"
    if recommendation is Recommendation.NO_REFUND:
        key: TemplateKey = reason.value  # type: ignore[assignment]  # NO_REFUND reasons are template keys
        return key
    return "MANUAL"


@dataclass(frozen=True)
class TemplateContext:
    first_name: str
    credit_union: str
    fee: FeeFacts | None  # None in manual cases without an identified fee
    claim_window_days: int


def render_template(key: TemplateKey, language: Language, context: TemplateContext) -> str:
    signature = _SIGNATURES[language].format(credit_union=context.credit_union)
    values: dict[str, object] = {
        "name": context.first_name,
        "signature": signature,
        "days": context.claim_window_days,
    }
    if context.fee is not None:
        values |= {
            "amount": money(context.fee.amount),
            "fee": _fee_name(context.fee.fee_type, language),
            "day": _long_day(context.fee.day, language),
        }
    return _TEMPLATES[(key, language)].format(**values)


def all_template_keys() -> list[tuple[TemplateKey, Language]]:
    return list(_TEMPLATES)


def _fee_name(kind: FeeType, language: Language) -> str:
    return _FEE_NAMES_ES[kind] if language == "es" else plain_name(kind)


def _long_day(on: date, language: Language) -> str:
    if language == "es":
        return f"{on.day} de {_MONTHS_ES[on.month - 1]}"
    return f"{_MONTHS_EN[on.month - 1]} {on.day}"

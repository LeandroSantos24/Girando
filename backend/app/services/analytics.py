"""Registro de eventos de producto. Sin PII en properties. Nunca bloquea la request si falla."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

from app.core.db import RequestContext, unit_of_work

log = logging.getLogger("girando.analytics")


def track(event: str, ctx: RequestContext, user_id=None, listing_id=None, agency_id=None, promotion_id=None,
          properties: dict[str, Any] | None = None, platform: str = "web") -> None:
    try:
        with unit_of_work("worker", None, ctx) as conn:
            conn.execute(text("""INSERT INTO app.analytics_events (event_name, user_id, platform, listing_id, agency_id, promotion_id, properties)
                                 VALUES (CAST(:e AS app.analytics_event_name), :u, CAST(:pf AS app.client_platform), :l, :a, :p, CAST(:props AS jsonb))"""),
                         {"e": event, "u": user_id, "pf": platform if platform in ("web", "ios", "android") else "web",
                          "l": listing_id, "a": agency_id, "p": promotion_id, "props": json.dumps(properties or {})})
    except Exception:  # noqa: BLE001
        log.warning("analytics_track_failed", extra={"event": event})

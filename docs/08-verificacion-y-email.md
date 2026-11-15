# Verificación de agencias y email (fase 3)

## Verificación (preparada, reglas finales pendientes)

Estados que ve el sistema (`app.agency_verification_state`): `none` (sin solicitud), `pending`, `review`, `verified`,
`rejected`, `suspended`, `revoked`. El sello **“Agencia verificada”** aparece solo si hay una aprobación real registrada
(`agencies.status = verified`, que únicamente cambia un miembro de staff desde el Admin).

Flujo:

1. La agencia pide la verificación (Mi Girando → Verificación). Una sola solicitud abierta por agencia.
2. Admin → Verificaciones → Ver → **Tomar revisión** (pasa a `review` y se asigna a quien revisa).
3. Checklist: se tilda cada punto y se dejan notas de evidencia (qué se revisó, dónde, con quién). Todo queda en Auditoría.
4. **Verificar** (pide nota de aprobación) o **Rechazar** (pide motivo). Admin puede después suspender o revocar.

Checklist preliminar (editable en `verification_products.checklist_template`): CUIT y razón social, domicilio comercial,
habilitación municipal, identidad del responsable, teléfono/WhatsApp y email.

**No están definidas** (decisión del negocio/legal, no del sistema): qué documentación es obligatoria, si el checklist completo es
requisito para aprobar, vigencia del sello, costo, y dónde se guardan los documentos (está previsto un bucket privado R2 con URLs firmadas).

## Email

Remitentes separados por tipo (`app/integrations/email.py`, variables `EMAIL_FROM_*`):

| Tipo | Remitente por defecto | Uso |
|---|---|---|
| Transaccional | `contacto.avisos@girando.app` | Verificación de email, recuperar contraseña, moderación, vencimientos, pagos |
| Oficial | `contacto.oficial@girando.app` | Comunicaciones institucionales (términos, cambios importantes) |
| Contacto | `contacto@girando.app` | `Reply-To` de los anteriores |
| Marketing | sin configurar | Solo a usuarios con consentimiento `marketing_communications` vigente; sin remitente configurado no se envía nada |

Todos los envíos pasan por la cola `email_events` (Admin → Cola de envíos). Sin proveedor configurado quedan en la cola como
“Sin proveedor”. Para producción falta: elegir proveedor (ej. Resend), verificar el dominio (SPF, DKIM, DMARC) y crear las casillas.

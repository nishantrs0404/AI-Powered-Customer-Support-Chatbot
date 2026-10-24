"""Intent-aware context builder for grounded reply generation.

Examines the classified intent and extracted entities to decide which
business records are relevant, retrieves them via the retrieval service,
and assembles a structured context object that the reply pipeline can
inject into the Gemini prompt.
"""

from typing import Any, Optional

from app.services.retrieval import (
    get_cancellation_policy,
    get_refund_policy,
    get_return_policy,
    get_shipping_policy,
    lookup_order,
    lookup_product,
    lookup_shipment,
)

# Intents that benefit from business-data lookups.
_ORDER_INTENTS = {"order_status", "cancel_order", "refund", "return"}
_SHIPPING_INTENTS = {"shipping", "order_status"}
_PRODUCT_INTENTS = {"product_info"}
_POLICY_INTENTS = {"return", "refund", "cancel_order", "shipping"}
# Intents that should *not* trigger any business-data lookup.
_SKIP_INTENTS = {"greeting", "unknown"}


def build_context(
    message: str,
    intent: str,
    entities: dict[str, list[str]],
) -> dict[str, Any]:
    """Build a structured context object for the reply pipeline.

    Parameters
    ----------
    message:
        The original customer message.
    intent:
        The classified intent string (e.g. ``"order_status"``).
    entities:
        Dictionary of extracted entities with lists of values,
        as returned by ``ExtractedEntities.to_dict()``.

    Returns
    -------
    dict
        A context dictionary with the following possible keys:

        - ``"intent"`` — echo of the intent used for the lookup.
        - ``"order"`` — matched order record or ``None``.
        - ``"shipment"`` — matched shipment record or ``None``.
        - ``"product"`` — matched product record or ``None``.
        - ``"return_policy"`` — return policy when relevant.
        - ``"refund_policy"`` — refund policy when relevant.
        - ``"cancellation_policy"`` — cancellation policy when relevant.
        - ``"shipping_policy"`` — shipping policy when relevant.
        - ``"data_retrieved"`` — ``True`` if any business record was found.
        - ``"missing_info"`` — list of strings describing information
          that was expected but could not be found.
    """
    context: dict[str, Any] = {"intent": intent}
    missing: list[str] = []

    # Fast exit for intents that never need business data.
    if intent in _SKIP_INTENTS:
        context["data_retrieved"] = False
        context["missing_info"] = []
        return context

    order_ids: list[str] = entities.get("order_ids", [])
    tracking_numbers: list[str] = entities.get("tracking_numbers", [])
    products: list[str] = entities.get("products", [])

    # ------------------------------------------------------------------
    # Order lookup
    # ------------------------------------------------------------------
    if intent in _ORDER_INTENTS:
        if order_ids:
            order = lookup_order(order_ids[0])
            context["order"] = order
            if order is None:
                missing.append(f"No order found for ID '{order_ids[0]}'.")
        else:
            context["order"] = None
            missing.append("No order ID was provided by the customer.")

    # ------------------------------------------------------------------
    # Shipment / tracking lookup
    # ------------------------------------------------------------------
    if intent in _SHIPPING_INTENTS or tracking_numbers:
        shipment = None

        if tracking_numbers:
            shipment = lookup_shipment(tracking_number=tracking_numbers[0])
        elif order_ids:
            shipment = lookup_shipment(order_id=order_ids[0])

        context["shipment"] = shipment
        if shipment is None and (tracking_numbers or order_ids):
            missing.append("No shipment information found for the provided identifier.")

    # ------------------------------------------------------------------
    # Product lookup
    # ------------------------------------------------------------------
    if intent in _PRODUCT_INTENTS or products:
        product = None
        if products:
            product = lookup_product(product_name=products[0])
        context["product"] = product
        if product is None and products:
            missing.append(f"No product information found for '{products[0]}'.")

    # ------------------------------------------------------------------
    # Policy retrieval
    # ------------------------------------------------------------------
    if intent in _POLICY_INTENTS:
        if intent == "return":
            context["return_policy"] = get_return_policy()
        elif intent == "refund":
            context["refund_policy"] = get_refund_policy()
        elif intent == "cancel_order":
            context["cancellation_policy"] = get_cancellation_policy()
        elif intent == "shipping":
            context["shipping_policy"] = get_shipping_policy()

    # General shipping policy for order_status when shipment exists.
    # (Intentionally not duplicated — only added when it would help.)

    # ------------------------------------------------------------------
    # Summary flags
    # ------------------------------------------------------------------
    data_keys = {"order", "shipment", "product", "return_policy",
                 "refund_policy", "cancellation_policy", "shipping_policy"}
    context["data_retrieved"] = any(
        context.get(key) is not None for key in data_keys
    )
    context["missing_info"] = missing

    return context


def format_context_for_prompt(context: dict[str, Any]) -> str:
    """Serialize the context dict into a text block suitable for Gemini.

    The output is a clearly delimited section so the model can
    distinguish retrieved business facts from the customer message.
    Returns an empty string when no data was retrieved.
    """
    if not context.get("data_retrieved"):
        parts = []
        if context.get("missing_info"):
            parts.append("Note: " + " ".join(context["missing_info"]))
        return "\n".join(parts)

    lines: list[str] = ["=== RETRIEVED BUSINESS DATA (use these facts only) ==="]

    intent = context.get("intent", "")

    # Order
    order = context.get("order")
    if order:
        lines.append(f"\n[Order Record]")
        lines.append(f"  Order ID: {order.get('order_id', 'N/A')}")
        lines.append(f"  Status: {order.get('status', 'N/A')}")
        lines.append(f"  Total: {order.get('total', 'N/A')}")
        lines.append(f"  Placed: {order.get('placed_at', 'N/A')}")
        lines.append(f"  Last Updated: {order.get('updated_at', 'N/A')}")
        items = order.get("items", [])
        if items:
            lines.append("  Items:")
            for item in items:
                lines.append(f"    - {item.get('name', '?')} x{item.get('quantity', '?')} ({item.get('price', '?')})")

    # Shipment
    shipment = context.get("shipment")
    if shipment:
        lines.append(f"\n[Shipment Record]")
        lines.append(f"  Tracking Number: {shipment.get('tracking_number', 'N/A')}")
        lines.append(f"  Carrier: {shipment.get('carrier', 'N/A')}")
        lines.append(f"  Status: {shipment.get('status', 'N/A')}")
        lines.append(f"  Estimated Delivery: {shipment.get('estimated_delivery', 'N/A')}")
        lines.append(f"  Shipped At: {shipment.get('shipped_at', 'N/A')}")
        delivered = shipment.get("delivered_at")
        if delivered:
            lines.append(f"  Delivered At: {delivered}")

    # Product
    product = context.get("product")
    if product:
        lines.append(f"\n[Product Record]")
        lines.append(f"  Name: {product.get('name', 'N/A')}")
        lines.append(f"  Price: {product.get('price', 'N/A')}")
        lines.append(f"  In Stock: {'Yes' if product.get('in_stock') else 'No'}")
        lines.append(f"  Description: {product.get('description', 'N/A')}")
        lines.append(f"  Warranty: {product.get('warranty', 'N/A')}")

    # Policies
    for policy_key in ("return_policy", "refund_policy", "cancellation_policy", "shipping_policy"):
        policy = context.get(policy_key)
        if policy:
            lines.append(f"\n[{policy.get('title', policy_key)}]")
            for k, v in policy.items():
                if k == "title":
                    continue
                if isinstance(v, list):
                    lines.append(f"  {k}:")
                    for item in v:
                        lines.append(f"    - {item}")
                else:
                    lines.append(f"  {k}: {v}")

    lines.append("\n=== END RETRIEVED BUSINESS DATA ===")

    # Append any missing-info notes.
    if context.get("missing_info"):
        lines.append("\nNote: " + " ".join(context["missing_info"]))

    return "\n".join(lines)

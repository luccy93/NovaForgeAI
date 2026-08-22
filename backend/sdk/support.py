"""Support SDK mixin — Customer Support & Service Management (Volume 54)."""

from __future__ import annotations


class SupportMixin:
    def support_create_ticket(self, customer_id, subject, description="", category=None,
                              priority="normal", severity=None, source="web", **kwargs):
        return self._post("/support/tickets", json={
            "customer_id": customer_id, "subject": subject, "description": description,
            "category": category, "priority": priority, "severity": severity,
            "source": source, **kwargs,
        })

    def support_list_tickets(self, status=None, priority=None, category=None,
                             customer_id=None, limit=50, offset=0, **kwargs):
        params = {"limit": limit, "offset": offset, **kwargs}
        if status: params["status"] = status
        if priority: params["priority"] = priority
        if category: params["category"] = category
        if customer_id: params["customer_id"] = customer_id
        return self._get("/support/tickets", params=params)

    def support_get_ticket(self, ticket_id):
        return self._get(f"/support/tickets/{ticket_id}")

    def support_update_ticket(self, ticket_id, **kwargs):
        return self._put(f"/support/tickets/{ticket_id}", json=kwargs)

    def support_transition_ticket(self, ticket_id, new_status):
        return self._post(f"/support/tickets/{ticket_id}/transition", params={"new_status": new_status})

    def support_reply(self, ticket_id, message_text, sender_id, sender_type="customer", visibility="customer"):
        return self._post(f"/support/tickets/{ticket_id}/messages", json={
            "message_text": message_text, "sender_id": sender_id,
            "sender_type": sender_type, "visibility": visibility,
        })

    def support_list_messages(self, ticket_id, include_internal=False, limit=100):
        return self._get(f"/support/tickets/{ticket_id}/messages",
                         params={"include_internal": include_internal, "limit": limit})

    def support_assign(self, ticket_id, assigned_to, assigned_by, team=None):
        return self._post(f"/support/tickets/{ticket_id}/assign", json={
            "assigned_to": assigned_to, "assigned_by": assigned_by, "team": team,
        })

    def support_escalate(self, ticket_id, escalation_type, to_level, reason=""):
        return self._post(f"/support/tickets/{ticket_id}/escalate", json={
            "escalation_type": escalation_type, "to_level": to_level, "reason": reason,
        })

    def support_resolve(self, ticket_id):
        return self._post(f"/support/tickets/{ticket_id}/resolve")

    def support_close(self, ticket_id):
        return self._post(f"/support/tickets/{ticket_id}/close")

    def support_reopen(self, ticket_id):
        return self._post(f"/support/tickets/{ticket_id}/reopen")

    def support_link_ticket(self, ticket_id, link_type, target_id, target_url=None):
        return self._post(f"/support/tickets/{ticket_id}/link", json={
            "link_type": link_type, "target_id": target_id, "target_url": target_url,
        })

    def support_classify(self, ticket_id):
        return self._post(f"/support/tickets/{ticket_id}/classify")

    def support_ai_suggest(self, ticket_id):
        return self._get(f"/support/tickets/{ticket_id}/ai-suggest")

    def support_search(self, query, limit=50):
        return self._post("/support/tickets/search", json={"query": query, "limit": limit})

    def support_create_article(self, title, content="", category="faq", **kwargs):
        return self._post("/support/knowledge/articles", json={
            "title": title, "content": content, "category": category, **kwargs,
        })

    def support_list_articles(self, category=None, product=None, status=None, limit=50):
        params = {"limit": limit}
        if category: params["category"] = category
        if product: params["product"] = product
        if status: params["status"] = status
        return self._get("/support/knowledge/articles", params=params)

    def support_search_knowledge(self, query, category=None, product=None, limit=20):
        return self._post("/support/knowledge/search", json={
            "query": query, "category": category, "product": product, "limit": limit,
        })

    def support_create_sla_policy(self, name, priority, first_response_minutes, resolution_minutes, **kwargs):
        return self._post("/support/sla/policies", json={
            "name": name, "priority": priority,
            "first_response_minutes": first_response_minutes,
            "resolution_minutes": resolution_minutes, **kwargs,
        })

    def support_sla_status(self, ticket_id):
        return self._get(f"/support/sla/tracking/{ticket_id}")

    def support_sla_summary(self):
        return self._get("/support/sla/summary")

    def support_submit_feedback(self, ticket_id, customer_id, rating, feedback_type="csat", comment=None):
        return self._post("/support/feedback", json={
            "ticket_id": ticket_id, "customer_id": customer_id,
            "rating": rating, "feedback_type": feedback_type, "comment": comment,
        })

    def support_analytics(self):
        return self._get("/support/analytics")

    def support_status(self):
        return self._get("/support/status")

    def support_customer_tickets(self, customer_id, limit=50):
        return self._get(f"/support/customer/{customer_id}/tickets", params={"limit": limit})

    def support_routing_queues(self):
        return self._get("/support/routing/queues")


class AsyncSupportMixin:
    async def support_create_ticket(self, customer_id, subject, description="", category=None,
                                    priority="normal", severity=None, source="web", **kwargs):
        return await self._post("/support/tickets", json={
            "customer_id": customer_id, "subject": subject, "description": description,
            "category": category, "priority": priority, "severity": severity,
            "source": source, **kwargs,
        })

    async def support_list_tickets(self, status=None, priority=None, limit=50, offset=0):
        params = {"limit": limit, "offset": offset}
        if status: params["status"] = status
        if priority: params["priority"] = priority
        return await self._get("/support/tickets", params=params)

    async def support_get_ticket(self, ticket_id):
        return await self._get(f"/support/tickets/{ticket_id}")

    async def support_reply(self, ticket_id, message_text, sender_id, sender_type="customer"):
        return await self._post(f"/support/tickets/{ticket_id}/messages", json={
            "message_text": message_text, "sender_id": sender_id, "sender_type": sender_type,
        })

    async def support_search_knowledge(self, query, limit=20):
        return await self._post("/support/knowledge/search", json={"query": query, "limit": limit})

    async def support_analytics(self):
        return await self._get("/support/analytics")

    async def support_status(self):
        return await self._get("/support/status")

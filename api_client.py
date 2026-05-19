"""dps-store 가먼트 프린터 API 클라이언트."""

import logging

import requests

logger = logging.getLogger(__name__)

VERSION = "1.0.0"


class GarmentApiClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"
        self.session.headers["X-Client-Version"] = VERSION

    def get_pending_jobs(
        self,
        limit: int = 10,
        garment_enabled: bool = True,
        work_order_enabled: bool = True,
    ) -> dict:
        """미출력 가먼트 큐 조회.

        garment_enabled / work_order_enabled — 클라이언트의 capability.
        서버는 capable 한 sub 만 OR 조건/선점 대상으로 사용하므로,
        예: work_order_enabled=False 인 PC 가 work_order 만 PENDING 인 큐에 묶여 무한 루프 도는 문제를 차단.
        """
        resp = self.session.get(
            f"{self.base_url}/api/printer/garment",
            params={
                "status": "pending",
                "limit": limit,
                "garment_enabled": "true" if garment_enabled else "false",
                "work_order_enabled": "true" if work_order_enabled else "false",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def mark_printed(self, job_id: str, target: str):
        """출력 완료 보고. target: "garment" | "workOrder"."""
        resp = self.session.post(
            f"{self.base_url}/api/printer/garment/{job_id}/printed",
            json={"target": target},
            timeout=10,
        )
        resp.raise_for_status()

    def mark_failed(self, job_id: str, target: str, reason: str = ""):
        """출력 실패 보고. target: "garment" | "workOrder"."""
        body = {"target": target}
        if reason:
            body["reason"] = reason
        resp = self.session.post(
            f"{self.base_url}/api/printer/garment/{job_id}/failed",
            json=body,
            timeout=10,
        )
        resp.raise_for_status()

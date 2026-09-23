
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

    def mark_downloaded(self, job_id: str, target: str):
        resp = self.session.post(
            f"{self.base_url}/api/printer/garment/{job_id}/downloaded",
            json={"target": target},
            timeout=10,
        )
        resp.raise_for_status()

    def mark_printed(self, job_id: str, target: str):
        resp = self.session.post(
            f"{self.base_url}/api/printer/garment/{job_id}/printed",
            json={"target": target},
            timeout=10,
        )
        resp.raise_for_status()

    def delete_job(self, job_id: str) -> dict:
        resp = self.session.delete(
            f"{self.base_url}/api/printer/garment/{job_id}",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def mark_failed(self, job_id: str, target: str, reason: str = ""):
        body = {"target": target}
        if reason:
            body["reason"] = reason
        resp = self.session.post(
            f"{self.base_url}/api/printer/garment/{job_id}/failed",
            json=body,
            timeout=10,
        )
        resp.raise_for_status()

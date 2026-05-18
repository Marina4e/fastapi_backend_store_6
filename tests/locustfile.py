from __future__ import annotations

from random import randint

from locust import HttpUser, between, task


class StoreBuyer(HttpUser):
    wait_time = between(0.001, 0.02)

    def on_start(self) -> None:
        self.product_id = 42

    @task(10)
    def purchase_product(self) -> None:
        payload = {
            "user_id": randint(1, 10_000_000),
            "product_id": self.product_id,
            "purchased_count": 1,
        }
        with self.client.post("/purchase", json=payload, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 409:
                response.success()
            else:
                response.failure(f"Unexpected status code: {response.status_code}")

    @task(1)
    def read_product(self) -> None:
        self.client.get(f"/products/{self.product_id}", name="/products/{product_id}")

    @task(1)
    def read_dependencies(self) -> None:
        self.client.get("/system/dependencies")

from __future__ import annotations

from random import randint

import gevent
from locust import FastHttpUser, between, events, task


class StoreBuyer(FastHttpUser):
    wait_time = between(0.001, 0.02)
    product_id = 42
    out_of_stock_seen = False

    def on_start(self) -> None:
        self.product_id = type(self).product_id

    @task(10)
    def purchase_product(self) -> None:
        payload = {
            "user_id": randint(1, 10_000_000),
            "product_id": self.product_id,
            "purchased_count": 1,
        }
        with self.client.post(
            "/purchase",
            json=payload,
            name="/purchase [attempt]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.request_meta["name"] = "/purchase [success]" # type: ignore
                response.success()
            elif response.status_code == 409:
                response.request_meta["name"] = "/purchase [out_of_stock_409]" # type: ignore
                response.success()
                self.stop_test_after_stock_depleted()
            else:
                response.failure(f"Unexpected status code: {response.status_code}") # type: ignore

    @task(1)
    def read_product(self) -> None:
        self.client.get(f"/products/{self.product_id}", name="/products/{product_id}")

    @task(1)
    def read_dependencies(self) -> None:
        self.client.get("/system/dependencies")

    def stop_test_after_stock_depleted(self) -> None:
        if type(self).out_of_stock_seen:
            return

        type(self).out_of_stock_seen = True
        runner = self.environment.runner
        if runner is None:
            return

        print("Stock is depleted: received 409 Conflict. Stopping Locust test.")
        if self.environment.web_ui is not None:
            gevent.spawn_later(0, runner.stop)
        else:
            gevent.spawn_later(0, runner.quit)


@events.test_start.add_listener
def reset_out_of_stock_flag(environment, **kwargs) -> None:
    StoreBuyer.out_of_stock_seen = False

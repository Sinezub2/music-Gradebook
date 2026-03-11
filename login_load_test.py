from locust import HttpUser, task, between
from bs4 import BeautifulSoup


class LoginUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        # each simulated user logs in once when spawned
        self.login()

    def get_csrf_token(self, response):
        soup = BeautifulSoup(response.text, "html.parser")
        return soup.find("input", {"name": "csrfmiddlewaretoken"})["value"]

    def login(self):
        # Step 1: load login page
        response = self.client.get("/login/")

        csrf_token = self.get_csrf_token(response)

        # Step 2: send login POST
        login_data = {
            "username": "test_teacher_1",
            "password": "testpassword123",
            "csrfmiddlewaretoken": csrf_token
        }

        headers = {
            "Referer": f"{self.host}/login/"
        }

        self.client.post("/login/", data=login_data, headers=headers)

    @task
    def visit_dashboard(self):
        # simulate activity after login
        self.client.get("/dashboard/")
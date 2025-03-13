from locust import HttpUser, task, between

class BiographyUser(HttpUser):
    wait_time = between(1, 5)
    host = "http://localhost:5000"

    @task
    def get_next_question(self):
        self.client.get("/biography/next-question", headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxLCJleHAiOjE3NDE5NTU0Mjh9.O50Jxp1rql52R-FWD3hiaMOu-yqyrB98DJQDv7Fl8zY"})

    @task
    def submit_answer(self):
        self.client.post("/biography/answer", json={"question_id": 1, "answer": "Test answer"}, headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxLCJleHAiOjE3NDE5NTU0Mjh9.O50Jxp1rql52R-FWD3hiaMOu-yqyrB98DJQDv7Fl8zY"})
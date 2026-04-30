from django.contrib.auth.models import User
from django.test import TestCase
from uuid import uuid4
from .models import RobotDevice


def unique_user(prefix: str = "robot"):
    token = uuid4().hex[:10]
    return f"{prefix}_{token}", f"{prefix}_{token}@example.com"


class AuthApiTests(TestCase):
    def test_register_returns_tokens_and_does_not_store_plaintext_password(self):
        username, email = unique_user()
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": username,
                "email": email.upper(),
                "password": "secret123",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["ok"])
        self.assertTrue(response.data["authenticated"])
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

        user = User.objects.get(username=username)
        self.assertEqual(user.email, email.lower())
        self.assertTrue(user.check_password("secret123"))
        self.assertEqual(user.profile.password_plaintext, "")
        self.assertEqual(user.profile.password_hash, user.password)

    def test_login_accepts_email_or_username_case_insensitive(self):
        username, email = unique_user()
        User.objects.create_user(
            username=username,
            email=email,
            password="secret123",
        )

        email_response = self.client.post(
            "/api/auth/login/",
            {"identifier": email.upper(), "password": "secret123"},
            content_type="application/json",
        )
        username_response = self.client.post(
            "/api/auth/login/",
            {"identifier": username.upper(), "password": "secret123"},
            content_type="application/json",
        )

        self.assertEqual(email_response.status_code, 200)
        self.assertEqual(username_response.status_code, 200)
        self.assertIn("access", email_response.data)
        self.assertIn("access", username_response.data)

    def test_login_rejects_bad_password(self):
        username, email = unique_user()
        User.objects.create_user(
            username=username,
            email=email,
            password="secret123",
        )

        response = self.client.post(
            "/api/auth/login/",
            {"identifier": email, "password": "wrongpass"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"], "Invalid credentials")

    def test_login_saves_robot_ip_to_session_and_database(self):
        username, email = unique_user()
        user = User.objects.create_user(
            username=username,
            email=email,
            password="secret123",
        )

        response = self.client.post(
            "/api/auth/login/",
            {
                "identifier": email,
                "password": "secret123",
                "robot_ip": "100.95.128.237",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["robot_ip"], "100.95.128.237")
        self.assertEqual(response.data["robot_url"], "http://100.95.128.237:9000")
        self.assertEqual(self.client.session["robot_ip"], "100.95.128.237")
        self.assertTrue(
            RobotDevice.objects.filter(
                user=user,
                ip="100.95.128.237",
                url="http://100.95.128.237:9000",
            ).exists()
        )

    def test_me_returns_authenticated_user_for_bearer_token(self):
        username, email = unique_user()
        register_response = self.client.post(
            "/api/auth/register/",
            {
                "username": username,
                "email": email,
                "password": "secret123",
            },
            content_type="application/json",
        )
        token = register_response.data["access"]

        response = self.client.get(
            "/api/auth/me/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["authenticated"])
        self.assertEqual(response.data["username"], username)

    def test_me_returns_guest_without_token(self):
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["authenticated"])
        self.assertEqual(response.data["username"], "Guest")

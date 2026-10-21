from datetime import time
from rest_framework.test import APITestCase
from core.models import *


def mkuser(email, role, name="X"):
    return User.objects.create_user(username=email, email=email, password="Senha@12345", role=role, first_name=name)


class ApiTests(APITestCase):
    def setUp(self):
        self.mgr, self.co, self.co2 = mkuser("m@x.com", "manager"), mkuser("c@x.com", "coordinator"), mkuser("c2@x.com", "coordinator")
        self.pu = mkuser("p@x.com", "professor"); self.prof = Professor.objects.create(user=self.pu)
        self.slot = Slot.objects.create(weekday=0, start=time(8), end=time(9))
    def as_(self, u): self.client.force_authenticate(u)

    def test_login_and_wrong_password(self):
        self.assertEqual(self.client.post("/api/auth/login/", {"email": "m@x.com", "password": "Senha@12345"}).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/login/", {"email": "m@x.com", "password": "no"}).status_code, 400)
    def test_requires_auth(self): self.assertEqual(self.client.get("/api/courses/").status_code, 401)
    def test_professor_cannot_write_or_read_admin(self):
        self.as_(self.pu)
        self.assertEqual(self.client.post("/api/courses/", {"name": "A", "code": "A"}).status_code, 403)
        self.assertEqual(self.client.get("/api/users/").status_code, 403)
        self.assertEqual(self.client.post("/api/rooms/", {"name": "S", "capacity": 5}).status_code, 403)
    def test_coordinator_writes_rooms_not_slots(self):
        self.as_(self.co)
        self.assertEqual(self.client.post("/api/rooms/", {"name": "S", "capacity": 5}).status_code, 201)
        self.assertEqual(self.client.post("/api/slots/", {"weekday": 1, "start": "08:00", "end": "09:00"}).status_code, 403)
        self.as_(self.mgr)
        self.assertEqual(self.client.post("/api/rooms/", {"name": "S2", "capacity": 5}).status_code, 403)
        self.assertEqual(self.client.post("/api/subjects/", {"name": "D", "code": "D", "course": 1}).status_code, 403)
    def test_coordinator_scope(self):
        self.as_(self.co); r = self.client.post("/api/courses/", {"name": "SI", "code": "SI"}); self.assertEqual(r.status_code, 201)
        cid = r.data["id"]
        self.as_(self.co2); self.assertEqual(self.client.get("/api/courses/").data, [])
        r = self.client.post("/api/subjects/", {"name": "D", "code": "D", "course": cid, "weekly_lessons": 2, "lesson_minutes": 50})
        self.assertEqual(r.status_code, 400)
    def test_subject_crud_and_duplicate_code(self):
        self.as_(self.co); cid = self.client.post("/api/courses/", {"name": "SI", "code": "SI"}).data["id"]
        d = {"name": "BD", "code": "BD", "course": cid, "weekly_lessons": 2, "lesson_minutes": 50}
        self.assertEqual(self.client.post("/api/subjects/", d).status_code, 201)
        self.assertEqual(self.client.post("/api/subjects/", d).status_code, 400)
    def test_professor_created_by_manager_only(self):
        d = {"full_name": "Ana", "email": "ana@x.com", "password": "Senha@12345", "max_weekly_hours": 12}
        self.as_(self.co); self.assertEqual(self.client.post("/api/professors/", d).status_code, 403)
        self.as_(self.mgr); r = self.client.post("/api/professors/", d); self.assertEqual(r.status_code, 201, r.data)
        listed = {u["email"]: u for u in self.client.get("/api/users/").data}
        self.assertEqual((listed["ana@x.com"]["role"], listed["ana@x.com"]["professor_id"]), ("professor", r.data["id"]))
        self.assertEqual(self.client.post("/api/professors/", {**d, "full_name": "B"}).status_code, 400)  # e-mail duplicado
        self.assertEqual(self.client.post("/api/professors/", {**d, "email": "b@x.com", "password": "12345678"}).status_code, 201)  # sem restrição de senha
    def test_coordinator_assigns_only_own_subjects(self):
        c1 = Course.objects.create(name="A", code="A", coordinator=self.co); c2 = Course.objects.create(name="B", code="B", coordinator=self.co2)
        s1 = Subject.objects.create(name="S1", code="S1", course=c1); s2 = Subject.objects.create(name="S2", code="S2", course=c2)
        self.prof.subjects.add(s2); url = f"/api/professors/{self.prof.id}/subjects/"
        ids = lambda: set(self.prof.subjects.values_list("id", flat=True))
        self.as_(self.co)
        self.assertEqual(self.client.put(url, {"subjects": [s1.id]}).status_code, 200); self.assertEqual(ids(), {s1.id, s2.id})
        self.assertEqual(self.client.put(url, {"subjects": [s2.id]}).status_code, 400)  # curso de outro coordenador
        self.client.put(url, {"subjects": []}); self.assertEqual(ids(), {s2.id})  # vínculo alheio preservado
        self.as_(self.pu); self.assertEqual(self.client.put(url, {"subjects": [s1.id]}).status_code, 403)
    def test_availability_independent_of_subjects(self):
        self.assertEqual(self.prof.subjects.count(), 0); self.as_(self.pu)
        self.assertEqual(self.client.put("/api/availability/me/", {"slots": [self.slot.id]}).status_code, 200)
        self.as_(self.co)  # coordenador enxerga a disponibilidade para decidir a atribuição
        self.assertEqual(self.client.get(f"/api/professors/{self.prof.id}/availability/").data["slots"], [self.slot.id])
    def test_availability_save_reload_and_validation(self):
        self.as_(self.pu)
        self.assertEqual(self.client.put("/api/availability/me/", {"slots": [self.slot.id]}, format="json").status_code, 200)
        self.assertEqual(self.client.get("/api/availability/me/").data["slots"], [self.slot.id])
        self.assertEqual(self.client.put("/api/availability/me/", {"slots": [9999]}, format="json").status_code, 400)
        self.client.put("/api/availability/me/", {"slots": []}, format="json")
        self.assertEqual(self.prof.availability.count(), 0)
    def test_professor_sees_only_self(self):
        other = Professor.objects.create(user=mkuser("o@x.com", "professor"))
        self.as_(self.pu); self.assertEqual([p["id"] for p in self.client.get("/api/professors/").data], [self.prof.id])
        self.assertEqual(self.client.get(f"/api/professors/{other.id}/availability/").status_code, 404)
    def test_slot_validation(self):
        self.as_(self.mgr)
        self.assertEqual(self.client.post("/api/slots/", {"weekday": 1, "start": "10:00", "end": "09:00"}).status_code, 400)
        self.assertEqual(self.client.post("/api/slots/", {"weekday": 1, "start": "08:00", "end": "09:30"}).status_code, 201)
    def test_deactivate_and_delete(self):
        self.as_(self.mgr)
        r = self.client.patch(f"/api/professors/{self.prof.id}/", {"is_active": False}); self.assertEqual(r.status_code, 200, r.data)
        self.prof.refresh_from_db(); self.assertFalse(self.prof.is_active); self.assertFalse(self.prof.user.is_active)
        self.assertEqual(self.client.delete(f"/api/professors/{self.prof.id}/").status_code, 204)
        self.assertFalse(User.objects.filter(email="p@x.com").exists())
        self.assertEqual(self.client.delete(f"/api/users/{self.mgr.id}/").status_code, 400)
    def test_delete_blocked_by_relationships(self):
        c = Course.objects.create(name="A", code="A", coordinator=self.co); Subject.objects.create(name="S", code="S", course=c)
        self.as_(self.co); self.assertEqual(self.client.delete(f"/api/courses/{c.id}/").status_code, 409)
        self.assertEqual(self.client.delete(f"/api/subjects/{Subject.objects.get().id}/").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/courses/{c.id}/").status_code, 204)
    def test_delete_slot_removes_availability(self):
        Availability.objects.create(professor=self.prof, slot=self.slot); self.as_(self.mgr)
        self.assertEqual(self.client.delete(f"/api/slots/{self.slot.id}/").status_code, 204); self.assertEqual(self.prof.availability.count(), 0)
    def test_dashboard_real_numbers(self):
        self.as_(self.mgr); cards = {c["label"]: c["value"] for c in self.client.get("/api/dashboard/").data["cards"]}
        self.assertEqual(cards["Professores ativos"], 1)

    def test_change_password(self):
        self.as_(self.pu)
        self.assertEqual(self.client.post("/api/auth/password/", {"current": "errada", "new": "1"}).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/password/", {"current": "Senha@12345", "new": "1234"}).status_code, 200)
        from rest_framework.test import APIClient
        self.assertEqual(APIClient().post("/api/auth/login/", {"email": "p@x.com", "password": "1234"}, format="json").status_code, 200)
    def test_professor_edits_own_basic_profile(self):
        self.as_(self.pu)
        r = self.client.patch("/api/profile/me/", {"full_name": "Novo Nome", "institutional_id": "123"}); self.assertEqual(r.status_code, 200)
        self.pu.refresh_from_db(); self.prof.refresh_from_db()
        self.assertEqual((self.pu.first_name, self.prof.institutional_id), ("Novo Nome", "123"))
        self.assertEqual(self.client.patch("/api/profile/me/", {"full_name": " "}).status_code, 400)
        self.as_(self.co); self.assertEqual(self.client.patch("/api/profile/me/", {"full_name": "x"}).status_code, 403)
    def test_student_count(self):
        self.as_(self.co); cid = self.client.post("/api/courses/", {"name": "SI", "code": "SI"}).data["id"]
        r = self.client.post("/api/subjects/", {"name": "BD", "code": "BD", "course": cid}); self.assertEqual(r.data["student_count"], 30)
        self.assertEqual(self.client.post("/api/subjects/", {"name": "X", "code": "X", "course": cid, "student_count": 0}).status_code, 400)
    def test_deactivating_slot_clears_availability(self):
        Availability.objects.create(professor=self.prof, slot=self.slot)
        self.as_(self.mgr); self.client.patch(f"/api/slots/{self.slot.id}/", {"is_active": False})
        self.assertEqual(self.prof.availability.count(), 0)
    def test_pagination_only_with_page_param(self):
        self.as_(self.co)
        for i in range(12): Room.objects.create(name=f"S{i}", capacity=10)
        self.assertIsInstance(self.client.get("/api/rooms/").data, list)
        d = self.client.get("/api/rooms/?page=2").data; self.assertEqual((d["count"], len(d["results"])), (12, 2))
        self.assertEqual(self.client.get("/api/rooms/?page=1&search=S11").data["count"], 1)

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



class HybridSolverAndScheduleTests(APITestCase):
    def setUp(self):
        self.mgr = mkuser("mgr_s@x.com", "manager", "Gestor")
        self.co = mkuser("co_s@x.com", "coordinator", "Coordenador")
        self.course = Course.objects.create(name="Engenharia de Computação", code="EC", coordinator=self.co)

        # Create 10 slots across 5 days (2 per day, 60 min each)
        self.slots = []
        for day in range(5):
            self.slots.append(Slot.objects.create(weekday=day, start=time(8, 0), end=time(9, 0)))
            self.slots.append(Slot.objects.create(weekday=day, start=time(9, 0), end=time(10, 0)))

        # Create 3 professors
        self.p1_user = mkuser("p1@x.com", "professor", "Prof Alfa")
        self.p2_user = mkuser("p2@x.com", "professor", "Prof Beta")
        self.p3_user = mkuser("p3@x.com", "professor", "Prof Gama")
        self.p1 = Professor.objects.create(user=self.p1_user, max_weekly_hours=10)
        self.p2 = Professor.objects.create(user=self.p2_user, max_weekly_hours=10)
        self.p3 = Professor.objects.create(user=self.p3_user, max_weekly_hours=10)

    def as_(self, u):
        self.client.force_authenticate(u)

    def test_hybrid_sa_and_tabu_modes_via_api(self):
        s1 = Subject.objects.create(name="Algoritmos", code="ALG", course=self.course, weekly_lessons=3, preferred_days=[0, 2, 4])
        s2 = Subject.objects.create(name="Estrutura de Dados", code="ED", course=self.course, weekly_lessons=3, preferred_days=[1, 3])
        s3 = Subject.objects.create(name="Redes", code="RED", course=self.course, weekly_lessons=2)

        self.p1.subjects.add(s1)
        self.p2.subjects.add(s2)
        self.p3.subjects.add(s3)

        # Give availability to professors
        for sl in self.slots[:6]:
            Availability.objects.create(professor=self.p1, slot=sl)
        for sl in self.slots[2:8]:
            Availability.objects.create(professor=self.p2, slot=sl)
        for sl in self.slots[4:]:
            Availability.objects.create(professor=self.p3, slot=sl)

        self.as_(self.co)
        for algo in ("hybrid", "sa", "tabu"):
            r = self.client.post("/api/schedules/generate/", {"algorithm": algo, "seed": 42}, format="json")
            self.assertEqual(r.status_code, 201, r.data)
            data = r.data
            self.assertEqual(data["algorithm"], algo)
            self.assertEqual(data["total"], 8)
            self.assertEqual(len(data["alloc"]), 8)
            self.assertEqual(len(data["pending"]), 0)
            self.assertEqual(data["metrics"]["hard_conflicts"], 0)

            # Verify every allocated lesson respects professor availability and has no course/prof slot clash
            used_course_slots = set()
            used_prof_slots = set()
            for item in data["alloc"]:
                pid = item["professorId"]
                sid = item["slotId"]
                self.assertTrue(Availability.objects.filter(professor_id=pid, slot_id=sid).exists())
                self.assertNotIn((item["course"], sid), used_course_slots)
                self.assertNotIn((pid, sid), used_prof_slots)
                used_course_slots.add((item["course"], sid))
                used_prof_slots.add((pid, sid))

    def test_solver_escapes_local_minimum_and_optimizes_soft_constraints(self):
        from core.solver import HybridTimetableSolver

        # Scenario where initial placement with suboptimal soft constraints is refined by SA + Tabu Search
        slots_data = [
            {"id": i + 1, "weekday": i // 2, "start": f"0{8 + (i % 2)}:00:00", "end": f"0{9 + (i % 2)}:00:00", "duration_mins": 60}
            for i in range(8)
        ]
        subjects_data = [
            {"id": 1, "name": "Cálculo", "code": "CALC", "course_id": 1, "course_name": "EC", "weekly_lessons": 2, "preferred_days": [1, 3], "qualified_prof_ids": [1]},
            {"id": 2, "name": "Física", "code": "FIS", "course_id": 1, "course_name": "EC", "weekly_lessons": 2, "preferred_days": [0, 2], "qualified_prof_ids": [2]},
            {"id": 3, "name": "Química", "code": "QUI", "course_id": 1, "course_name": "EC", "weekly_lessons": 2, "preferred_days": [0, 1], "qualified_prof_ids": [1, 2]},
        ]
        profs_data = [
            {"id": 1, "full_name": "Prof 1", "max_weekly_mins": 240, "available_slot_ids": {1, 2, 3, 4, 5, 6, 7, 8}},
            {"id": 2, "full_name": "Prof 2", "max_weekly_mins": 240, "available_slot_ids": {1, 2, 3, 4, 5, 6, 7, 8}},
        ]

        solver = HybridTimetableSolver(slots_data, subjects_data, profs_data, mode="hybrid", seed=7)
        # Force an unoptimized starting state (all on wrong days, split professors, and unassigned)
        bad_initial = [(2, 1), (1, 2), (1, 3), (2, 4), None, None]
        bad_cost = solver.cost(bad_initial)

        sa_state, sa_cost, _ = solver.run_simulated_annealing(bad_initial, use_tabu_memory=True)
        ts_state, ts_cost, _ = solver.run_tabu_search(sa_state)

        self.assertLess(sa_cost, bad_cost)
        self.assertLessEqual(ts_cost, sa_cost)
        eval_res = solver.evaluate_detailed(ts_state)
        self.assertEqual(eval_res["unassigned"], 0)
        self.assertEqual(eval_res["course_conflicts"], 0)
        self.assertEqual(eval_res["prof_conflicts"], 0)

    def test_respects_max_weekly_hours_and_reports_pending_reason(self):
        # Professor has only 1h max_weekly_hours, but subject requires 3 lessons of 1h each
        self.p1.max_weekly_hours = 1
        self.p1.save()
        Availability.objects.create(professor=self.p1, slot=self.slots[0])
        Availability.objects.create(professor=self.p1, slot=self.slots[1])
        Availability.objects.create(professor=self.p1, slot=self.slots[2])

        Subject.objects.create(name="IA", code="IA", course=self.course, weekly_lessons=3)

        self.as_(self.co)
        r = self.client.post("/api/schedules/generate/", {"algorithm": "hybrid", "seed": 1}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(r.data["alloc"]), 1)
        self.assertEqual(len(r.data["pending"]), 1)
        self.assertEqual(r.data["pending"][0]["missing"], 2)
        self.assertIn("Carga horária semanal máxima", r.data["pending"][0]["reason"])

    def test_publish_archives_previous_and_professor_views_published_grid(self):
        s1 = Subject.objects.create(name="BD", code="BD", course=self.course, weekly_lessons=2)
        self.p1.subjects.add(s1)
        Availability.objects.create(professor=self.p1, slot=self.slots[0])
        Availability.objects.create(professor=self.p1, slot=self.slots[2])

        self.as_(self.co)
        p1_res = self.client.post("/api/schedules/generate/", {"algorithm": "hybrid"}, format="json")
        p2_res = self.client.post("/api/schedules/generate/", {"algorithm": "tabu"}, format="json")
        id1, id2 = p1_res.data["id"], p2_res.data["id"]

        # Professor sees nothing before publication
        self.as_(self.p1_user)
        self.assertEqual(self.client.get("/api/schedules/").data, [])
        self.assertEqual(self.client.post("/api/schedules/generate/", {}).status_code, 403)

        # Coordinator publishes first proposal, then second proposal
        self.as_(self.co)
        self.assertEqual(self.client.post(f"/api/schedules/{id1}/publish/").data["status"], "published")
        self.assertEqual(self.client.post(f"/api/schedules/{id2}/publish/").data["status"], "published")

        # First proposal must now be archived
        self.assertEqual(ScheduleProposal.objects.get(pk=id1).status, "archived")
        self.assertEqual(ScheduleProposal.objects.get(pk=id2).status, "published")

        # Professor now sees only the published proposal
        self.as_(self.p1_user)
        prof_schedules = self.client.get("/api/schedules/").data
        self.assertEqual(len(prof_schedules), 1)
        self.assertEqual(prof_schedules[0]["id"], id2)
        self.assertEqual(len(prof_schedules[0]["alloc"]), 2)

    def test_five_professors_similar_availability_fills_full_grid(self):
        from django.core.management import call_command
        from collections import Counter

        Subject.objects.all().delete()
        Course.objects.all().delete()
        Professor.objects.all().delete()
        Slot.objects.all().delete()
        call_command("seed_demo", force=True)
        coord = User.objects.get(email="coord@demo.com")
        self.as_(coord)

        # 1. Testar curso SI isolado: 20/20 aulas alocadas (100% da grade cheia) e publicar
        c_si = Course.objects.get(code="SI")
        c_cc = Course.objects.get(code="CC")
        r_si = self.client.post("/api/schedules/generate/", {"algorithm": "hybrid", "course_id": c_si.id, "seed": 42}, format="json")
        self.assertEqual(r_si.status_code, 201, r_si.data)
        self.assertEqual(r_si.data["course"], c_si.id)
        self.assertEqual(r_si.data["total"], 24)
        self.assertEqual(len(r_si.data["alloc"]), 24)
        self.assertEqual(len(r_si.data["pending"]), 0)
        self.assertEqual(r_si.data["metrics"]["hard_conflicts"], 0)
        self.assertEqual(r_si.data["metrics"]["split_subject_days"], 0)
        self.assertEqual(r_si.data["metrics"]["non_consecutive_lessons"], 0)

        counts = Counter(a["professorId"] for a in r_si.data["alloc"])
        self.assertEqual(len(counts), 5)
        for pid, count in counts.items():
            self.assertGreaterEqual(count, 2)

        # Publicar grade de SI
        pub_si = self.client.post(f"/api/schedules/{r_si.data['id']}/publish/")
        self.assertEqual(pub_si.data["status"], "published")

        # 2. Gerar grade do curso CC (respeitando horários já ocupados pelos professores na grade publicada de SI
        # e alocando também a Coordenadora que dá aula em CC-GPS)
        r_cc = self.client.post("/api/schedules/generate/", {"algorithm": "hybrid", "course_id": c_cc.id, "seed": 42}, format="json")
        self.assertEqual(r_cc.status_code, 201, r_cc.data)
        self.assertEqual(r_cc.data["course"], c_cc.id)
        self.assertEqual(r_cc.data["total"], 18)
        self.assertEqual(len(r_cc.data["alloc"]), 14)
        self.assertEqual(len(r_cc.data["pending"]), 2)
        for p_item in r_cc.data["pending"]:
            self.assertTrue(p_item.get("professor"))
            self.assertTrue(p_item.get("suggestion"))
        self.assertEqual(r_cc.data["metrics"]["hard_conflicts"], 0)
        self.assertEqual(r_cc.data["metrics"]["split_subject_days"], 0)
        self.assertEqual(r_cc.data["metrics"]["non_consecutive_lessons"], 0)

        # Verificar que a Coordenadora também foi alocada como docente em CC
        coord_prof = Professor.objects.get(user=coord)
        coord_lessons = [a for a in r_cc.data["alloc"] if a["professorId"] == coord_prof.id]
        self.assertEqual(len(coord_lessons), 2)

        # Publicar grade de CC e garantir que a grade publicada de SI NÃO foi arquivada (ambos os cursos publicados!)
        pub_cc = self.client.post(f"/api/schedules/{r_cc.data['id']}/publish/")
        self.assertEqual(pub_cc.data["status"], "published")
        self.assertEqual(ScheduleProposal.objects.get(pk=r_si.data["id"]).status, "published")
        self.assertEqual(ScheduleProposal.objects.get(pk=r_cc.data["id"]).status, "published")

        # Verificar que nenhum professor tem choque de horário entre as grades publicadas de SI e CC
        si_prof_slots = {(a["professorId"], a["slotId"]) for a in r_si.data["alloc"]}
        cc_prof_slots = {(a["professorId"], a["slotId"]) for a in r_cc.data["alloc"]}
        self.assertEqual(len(si_prof_slots & cc_prof_slots), 0)

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
        self.as_(self.co); self.assertEqual(self.client.patch("/api/profile/me/", {"full_name": "x"}).status_code, 200)
        self.as_(self.mgr); self.assertEqual(self.client.patch("/api/profile/me/", {"full_name": "x"}).status_code, 403)
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

        ia = Subject.objects.create(name="IA", code="IA", course=self.course, weekly_lessons=3)
        self.p1.subjects.add(ia)

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

    def test_five_courses_two_classes_each_staggered_professor_a(self):
        """
        5 cursos diferentes x 2 turmas por curso = 10 grades horárias (120 aulas semanais).
        Professor A leciona em 4 grades escalonadas:
          - Metaheurística na Turma A do Curso X (X-A)
          - Metaheurística na Turma B do Curso X (X-B)
          - Banco de Dados na Turma B do Curso Y (Y-B)
          - Python na Turma A do Curso Z (Z-A)
        E os demais professores (B..J) também lecionam de forma escalonada entre os 5 cursos.
        Testa tanto a geração global simultânea quanto a geração/publicação sequencial turma a turma.
        """
        ScheduleProposal.objects.all().delete()
        Availability.objects.all().delete()
        Subject.objects.all().delete()
        Course.objects.all().delete()
        Professor.objects.all().delete()
        Slot.objects.all().delete()

        times = [
            (time(8, 0), time(9, 0)),
            (time(9, 0), time(10, 0)),
            (time(10, 0), time(11, 0)),
            (time(11, 0), time(12, 0)),
        ]
        slots_by_day = {}
        all_slots = []
        for d in range(5):
            slots_by_day[d] = []
            for s_t, e_t in times:
                sl = Slot.objects.create(weekday=d, start=s_t, end=e_t, is_active=True)
                slots_by_day[d].append(sl)
                all_slots.append(sl)

        course_defs = [
            ("X", "Ciência da Computação"),
            ("Y", "Sistemas de Informação"),
            ("Z", "Engenharia de Software"),
            ("W", "Ciência de Dados"),
            ("V", "Inteligência Artificial"),
        ]
        turmas = {}
        for c_code, c_name in course_defs:
            for t in ("A", "B"):
                k = f"{c_code}-{t}"
                turmas[k] = Course.objects.create(
                    code=k,
                    name=f"Curso {c_code} ({c_name}) - Turma {t}",
                    coordinator=self.co,
                    is_active=True,
                )

        profs = {}
        for p_code in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]:
            u = mkuser(f"prof_{p_code.lower()}_esc@x.com", "professor", f"Professor {p_code}")
            profs[p_code] = Professor.objects.create(
                user=u, institutional_id=f"DOC-{p_code}", max_weekly_hours=14, is_active=True
            )

        grid_spec = {
            "X-A": [
                ("X-A-MET", "Metaheurística", "A", [0, 1]),
                ("X-A-BD",  "Banco de Dados", "B", [0, 2]),
                ("X-A-PY",  "Python", "C", [1, 3]),
                ("X-A-IA",  "Inteligência Artificial", "D", [2, 4]),
                ("X-A-RED", "Redes de Computadores", "E", [3, 4]),
                ("X-A-ES",  "Engenharia de Software", "F", [0, 4]),
            ],
            "X-B": [
                ("X-B-MET", "Metaheurística", "A", [0, 1]),
                ("X-B-BD",  "Banco de Dados", "B", [1, 3]),
                ("X-B-PY",  "Python", "D", [0, 2]),
                ("X-B-IA",  "Inteligência Artificial", "E", [1, 4]),
                ("X-B-RED", "Redes de Computadores", "G", [2, 3]),
                ("X-B-ES",  "Engenharia de Software", "H", [3, 4]),
            ],
            "Y-A": [
                ("Y-A-BD",  "Banco de Dados", "B", [2, 4]),
                ("Y-A-MET", "Metaheurística", "C", [0, 2]),
                ("Y-A-SO",  "Sistemas Operacionais", "F", [1, 3]),
                ("Y-A-WEB", "Desenvolvimento Web", "G", [0, 4]),
                ("Y-A-SEG", "Segurança da Informação", "I", [1, 2]),
                ("Y-A-MAT", "Matemática Discreta", "J", [3, 4]),
            ],
            "Y-B": [
                ("Y-B-BD",  "Banco de Dados", "A", [1, 2]),
                ("Y-B-MET", "Metaheurística", "C", [2, 4]),
                ("Y-B-SO",  "Sistemas Operacionais", "F", [0, 2]),
                ("Y-B-WEB", "Desenvolvimento Web", "H", [1, 3]),
                ("Y-B-SEG", "Segurança da Informação", "I", [0, 3]),
                ("Y-B-MAT", "Matemática Discreta", "J", [2, 4]),
            ],
            "Z-A": [
                ("Z-A-PY",  "Python", "A", [2, 3]),
                ("Z-A-BD",  "Banco de Dados", "D", [1, 3]),
                ("Z-A-ES",  "Engenharia de Software", "E", [0, 2]),
                ("Z-A-ARQ", "Arquitetura de Software", "G", [1, 4]),
                ("Z-A-QA",  "Qualidade de Software", "H", [0, 2]),
                ("Z-A-DEV", "DevOps", "I", [3, 4]),
            ],
            "Z-B": [
                ("Z-B-PY",  "Python", "C", [1, 4]),
                ("Z-B-BD",  "Banco de Dados", "D", [3, 4]),
                ("Z-B-ES",  "Engenharia de Software", "F", [2, 4]),
                ("Z-B-ARQ", "Arquitetura de Software", "G", [0, 3]),
                ("Z-B-QA",  "Qualidade de Software", "I", [0, 4]),
                ("Z-B-DEV", "DevOps", "J", [1, 2]),
            ],
            "W-A": [
                ("W-A-EST", "Estatística", "B", [3, 4]),
                ("W-A-ML",  "Machine Learning", "E", [2, 3]),
                ("W-A-BIG", "Big Data", "F", [1, 4]),
                ("W-A-MIN", "Mineração de Dados", "H", [0, 4]),
                ("W-A-VIS", "Visualização de Dados", "I", [2, 3]),
                ("W-A-ETL", "Engenharia de Dados", "J", [0, 1]),
            ],
            "W-B": [
                ("W-B-EST", "Estatística", "C", [0, 3]),
                ("W-B-ML",  "Machine Learning", "D", [0, 4]),
                ("W-B-BIG", "Big Data", "G", [1, 2]),
                ("W-B-MIN", "Mineração de Dados", "H", [2, 3]),
                ("W-B-VIS", "Visualização de Dados", "I", [1, 4]),
                ("W-B-ETL", "Engenharia de Dados", "J", [0, 3]),
            ],
            "V-A": [
                ("V-A-DL",  "Deep Learning", "B", [0, 1]),
                ("V-A-NLP", "Processamento de Linguagem Natural", "D", [1, 2]),
                ("V-A-ROB", "Robótica", "E", [0, 3]),
                ("V-A-VC",  "Visão Computacional", "F", [0, 3]),
                ("V-A-AG",  "Agentes Autônomos", "G", [3, 4]),
                ("V-A-ET",  "Ética em IA", "J", [1, 4]),
            ],
            "V-B": [
                ("V-B-DL",  "Deep Learning", "B", [1, 4]),
                ("V-B-NLP", "Processamento de Linguagem Natural", "C", [1, 3]),
                ("V-B-ROB", "Robótica", "E", [1, 4]),
                ("V-B-VC",  "Visão Computacional", "F", [3, 4]),
                ("V-B-AG",  "Agentes Autônomos", "H", [0, 1]),
                ("V-B-ET",  "Ética em IA", "I", [1, 3]),
            ],
        }

        for t_key, items in grid_spec.items():
            c_obj = turmas[t_key]
            for s_code, s_name, p_code, pref in items:
                s = Subject.objects.create(
                    code=s_code, name=s_name, course=c_obj,
                    weekly_lessons=2, lesson_minutes=60, student_count=35,
                    preferred_days=pref, is_active=True
                )
                profs[p_code].subjects.add(s)

        prof_a_slots = [
            slots_by_day[0][0], slots_by_day[0][1],
            slots_by_day[0][2], slots_by_day[0][3],
            slots_by_day[1][0], slots_by_day[1][1],
            slots_by_day[2][2], slots_by_day[2][3],
        ]
        for sl in prof_a_slots:
            Availability.objects.create(professor=profs["A"], slot=sl)
        for p_code, p in profs.items():
            if p_code != "A":
                for sl in all_slots[:18]:
                    Availability.objects.create(professor=p, slot=sl)

        self.as_(self.co)

        # 1) Modo Global Simultâneo (todas as 10 turmas dos 5 cursos de uma só vez)
        r_global = self.client.post("/api/schedules/generate/", {"algorithm": "hybrid", "seed": 42}, format="json")
        self.assertEqual(r_global.status_code, 201)
        self.assertEqual(r_global.data["total"], 120)
        self.assertEqual(len(r_global.data["alloc"]), 120)
        self.assertEqual(len(r_global.data["pending"]), 0)
        self.assertEqual(r_global.data["metrics"]["hard_conflicts"], 0)
        self.assertEqual(r_global.data["metrics"]["non_consecutive_lessons"], 0)

        prof_a_allocs = [a for a in r_global.data["alloc"] if a["professorId"] == profs["A"].id]
        self.assertEqual(len(prof_a_allocs), 8)
        prof_a_courses = {a["courseId"] for a in prof_a_allocs}
        self.assertEqual(prof_a_courses, {turmas["X-A"].id, turmas["X-B"].id, turmas["Y-B"].id, turmas["Z-A"].id})
        self.assertEqual(len({a["slotId"] for a in prof_a_allocs}), 8)

        # 2) Modo Escalonado Sequencial (gerando e publicando cada uma das 10 turmas em sequência)
        ScheduleProposal.objects.all().delete()
        all_published_prof_slots = set()
        for t_key in grid_spec.keys():
            c_obj = turmas[t_key]
            r_c = self.client.post("/api/schedules/generate/", {"algorithm": "hybrid", "course_id": c_obj.id, "seed": 42}, format="json")
            self.assertEqual(r_c.status_code, 201)
            self.assertEqual(len(r_c.data["alloc"]), 12)
            self.assertEqual(len(r_c.data["pending"]), 0)
            pub_c = self.client.post(f"/api/schedules/{r_c.data['id']}/publish/")
            self.assertEqual(pub_c.data["status"], "published")
            for a in pub_c.data["alloc"]:
                pair = (a["professorId"], a["slotId"])
                self.assertNotIn(pair, all_published_prof_slots)
                all_published_prof_slots.add(pair)

        self.assertEqual(ScheduleProposal.objects.filter(status="published").count(), 10)


class BugRegressionTests(APITestCase):
    """Suite de regressão cobrindo explicitamente os 9 bugs corrigidos (BUG-01 a BUG-09) e choque temporal."""

    def setUp(self):
        self.mgr = mkuser("mgr_bug@x.com", "manager", "Gestor")
        self.co1 = mkuser("co1_bug@x.com", "coordinator", "Coord 1")
        self.co2 = mkuser("co2_bug@x.com", "coordinator", "Coord 2")
        self.c1 = Course.objects.create(name="Curso 1", code="C1", coordinator=self.co1)
        self.c2 = Course.objects.create(name="Curso 2", code="C2", coordinator=self.co2)

        self.slot0 = Slot.objects.create(weekday=0, start=time(8, 0), end=time(9, 0))
        self.slot1 = Slot.objects.create(weekday=0, start=time(9, 0), end=time(10, 0))

        self.pu = mkuser("prof_bug@x.com", "professor", "Prof Bug")
        self.prof = Professor.objects.create(user=self.pu, max_weekly_hours=10)
        Availability.objects.create(professor=self.prof, slot=self.slot0)
        Availability.objects.create(professor=self.prof, slot=self.slot1)

        self.s1 = Subject.objects.create(name="Matéria 1", code="M1", course=self.c1, weekly_lessons=1, lesson_minutes=60)
        self.s2 = Subject.objects.create(name="Matéria 2", code="M2", course=self.c2, weekly_lessons=1, lesson_minutes=60)
        self.prof.subjects.add(self.s1, self.s2)

    def as_(self, u):
        self.client.force_authenticate(u)

    def test_bug01_invalid_seed_validation(self):
        from core.solver import HybridTimetableSolver

        self.as_(self.co1)
        for bad_seed in ([1, 2], {"a": 1}, True, False):
            r = self.client.post(
                "/api/schedules/generate/",
                {"algorithm": "hybrid", "course_id": self.c1.id, "seed": bad_seed},
                format="json",
            )
            self.assertEqual(r.status_code, 400, f"Seed {bad_seed!r} deveria retornar 400")
            self.assertEqual(r.data, {"seed": "Seed inválido."})

        with self.assertRaises(ValueError):
            HybridTimetableSolver([], [], [], seed=[1, 2])
        with self.assertRaises(ValueError):
            HybridTimetableSolver([], [], [], seed={"a": 1})
        with self.assertRaises(ValueError):
            HybridTimetableSolver([], [], [], seed=True)

    def test_bug02_coordinator_idor_isolation_on_schedules(self):
        self.as_(self.co1)
        r_draft = self.client.post(
            "/api/schedules/generate/",
            {"algorithm": "hybrid", "course_id": self.c1.id, "seed": 1},
            format="json",
        )
        self.assertEqual(r_draft.status_code, 201)
        draft_id = r_draft.data["id"]

        # co2 tenta publicar ou deletar rascunho de curso de co1 -> bloqueado (403 ou 404)
        self.as_(self.co2)
        self.assertIn(self.client.post(f"/api/schedules/{draft_id}/publish/").status_code, (403, 404))
        self.assertIn(self.client.delete(f"/api/schedules/{draft_id}/").status_code, (403, 404))
        self.assertEqual(ScheduleProposal.objects.get(pk=draft_id).status, "draft")

        # Mesmo após co1 publicar a proposta (ficando visível na listagem), co2 não pode deletar nem republicar
        self.as_(self.co1)
        self.assertEqual(self.client.post(f"/api/schedules/{draft_id}/publish/").status_code, 200)

        self.as_(self.co2)
        self.assertIn(self.client.post(f"/api/schedules/{draft_id}/publish/").status_code, (403, 404))
        self.assertIn(self.client.delete(f"/api/schedules/{draft_id}/").status_code, (403, 404))
        self.assertTrue(ScheduleProposal.objects.filter(pk=draft_id, status="published").exists())

    def test_bug03_direct_schedule_write_blocked_and_serializer_readonly(self):
        from core.serializers import ScheduleProposalSerializer

        self.as_(self.co1)
        r = self.client.post(
            "/api/schedules/generate/",
            {"algorithm": "hybrid", "course_id": self.c1.id, "seed": 1},
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        pid = r.data["id"]

        # Tentativas de escrita direta nos endpoints padrões do ModelViewSet devem retornar 405
        self.assertEqual(
            self.client.post("/api/schedules/", {"status": "published", "alloc": []}, format="json").status_code,
            405,
        )
        self.assertEqual(
            self.client.put(f"/api/schedules/{pid}/", {"status": "published", "alloc": []}, format="json").status_code,
            405,
        )
        self.assertEqual(
            self.client.patch(f"/api/schedules/{pid}/", {"status": "published"}, format="json").status_code,
            405,
        )

        # ScheduleProposalSerializer deve ignorar injeção de campos sensíveis (read_only_fields)
        prop = ScheduleProposal.objects.get(pk=pid)
        orig_alloc = list(prop.alloc)
        orig_metrics = dict(prop.metrics)
        ser = ScheduleProposalSerializer(
            instance=prop,
            data={
                "status": "published",
                "total": 999,
                "alloc": [{"professorId": 999, "slotId": 999}],
                "pending": [{"hack": True}],
                "metrics": {"hard_conflicts": 999},
                "scope": "Hack",
                "algorithm": "hack",
            },
            partial=True,
        )
        self.assertTrue(ser.is_valid(), ser.errors)
        ser.save()
        prop.refresh_from_db()
        self.assertEqual(prop.status, "draft")
        self.assertEqual(prop.total, 1)
        self.assertEqual(prop.alloc, orig_alloc)
        self.assertEqual(prop.metrics, orig_metrics)

    def test_bug04_publish_toctou_conflict_and_overload_detection(self):
        # 1) Conflito de mesmo horário (TOCTOU): restringe disponibilidade ao slot0
        Availability.objects.filter(professor=self.prof, slot=self.slot1).delete()

        self.as_(self.co1)
        r1 = self.client.post("/api/schedules/generate/", {"course_id": self.c1.id, "seed": 1}, format="json")
        self.assertEqual(r1.status_code, 201)

        self.as_(self.co2)
        r2 = self.client.post("/api/schedules/generate/", {"course_id": self.c2.id, "seed": 1}, format="json")
        self.assertEqual(r2.status_code, 201)

        # Ambos os rascunhos alocaram self.prof no self.slot0 antes de qualquer publicação
        self.assertEqual(r1.data["alloc"][0]["slotId"], self.slot0.id)
        self.assertEqual(r2.data["alloc"][0]["slotId"], self.slot0.id)

        # Publica o primeiro (200 OK); o segundo deve falhar com 409 Conflict
        self.as_(self.co1)
        self.assertEqual(self.client.post(f"/api/schedules/{r1.data['id']}/publish/").status_code, 200)

        self.as_(self.co2)
        pub2 = self.client.post(f"/api/schedules/{r2.data['id']}/publish/")
        self.assertEqual(pub2.status_code, 409)
        self.assertIn("Conflito de horário", pub2.data["detail"])

        # 2) Estouro de max_weekly_hours entre grades concorrentes em slots distintos
        ScheduleProposal.objects.all().delete()
        self.prof.max_weekly_hours = 1  # 60 min no total
        self.prof.save(update_fields=["max_weekly_hours"])

        # Gera rascunho de c1 no slot0
        Availability.objects.filter(professor=self.prof).delete()
        Availability.objects.create(professor=self.prof, slot=self.slot0)
        self.as_(self.co1)
        d1 = self.client.post("/api/schedules/generate/", {"course_id": self.c1.id, "seed": 1}, format="json")
        self.assertEqual(d1.status_code, 201)

        # Gera rascunho de c2 no slot1 (ainda sem c1 publicada)
        Availability.objects.filter(professor=self.prof).delete()
        Availability.objects.create(professor=self.prof, slot=self.slot1)
        self.as_(self.co2)
        d2 = self.client.post("/api/schedules/generate/", {"course_id": self.c2.id, "seed": 1}, format="json")
        self.assertEqual(d2.status_code, 201)

        # Publica d1 (60 min) -> 200 OK; publicar d2 (+60 min = 120 min > 60 min) -> 409 Conflict
        self.as_(self.co1)
        self.assertEqual(self.client.post(f"/api/schedules/{d1.data['id']}/publish/").status_code, 200)

        self.as_(self.co2)
        pub_overload = self.client.post(f"/api/schedules/{d2.data['id']}/publish/")
        self.assertEqual(pub_overload.status_code, 409)
        self.assertIn("Sobrecarga de carga horária", pub_overload.data["detail"])

    def test_bug05_generate_without_course_id_respects_published_schedules(self):
        # Força c1 a alocar slot0 e publica
        Availability.objects.filter(professor=self.prof, slot=self.slot1).delete()
        self.as_(self.co1)
        r1 = self.client.post("/api/schedules/generate/", {"course_id": self.c1.id, "seed": 1}, format="json")
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(self.client.post(f"/api/schedules/{r1.data['id']}/publish/").status_code, 200)
        self.assertEqual(r1.data["alloc"][0]["slotId"], self.slot0.id)

        # Libera slot1 também na disponibilidade do professor
        Availability.objects.create(professor=self.prof, slot=self.slot1)

        # co2 gera a grade SEM passar course_id: deve respeitar que slot0 já está ocupado em c1
        self.as_(self.co2)
        r2 = self.client.post("/api/schedules/generate/", {"algorithm": "hybrid", "seed": 1}, format="json")
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(len(r2.data["alloc"]), 1)
        self.assertEqual(r2.data["alloc"][0]["slotId"], self.slot1.id)
        self.assertNotEqual(r2.data["alloc"][0]["slotId"], self.slot0.id)

    def test_bug06_subject_without_professor_not_allocated_to_random_professor(self):
        # Remove todos os vínculos de professores da disciplina s1, mantendo self.prof ativo e disponível
        self.prof.subjects.clear()

        self.as_(self.co1)
        r = self.client.post("/api/schedules/generate/", {"course_id": self.c1.id, "seed": 1}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(r.data["alloc"]), 0)
        self.assertEqual(len(r.data["pending"]), 1)
        self.assertEqual(r.data["pending"][0]["professor"], "Sem professor atribuído")
        self.assertIn("Sem professor atribuído", r.data["pending"][0]["professor"])

    def test_bug07_overlapping_slots_rejected_and_solver_prevents_temporal_clash(self):
        from core.solver import HybridTimetableSolver

        self.as_(self.mgr)
        # 08:30–09:30 sobrepõe 08:00–09:00 (self.slot0) na segunda-feira (weekday=0)
        r_overlap = self.client.post(
            "/api/slots/",
            {"weekday": 0, "start": "08:30", "end": "09:30"},
            format="json",
        )
        self.assertEqual(r_overlap.status_code, 400)

        # Atualizar o próprio slot0 para 08:00–08:50 deve funcionar sem falso positivo
        r_patch = self.client.patch(
            f"/api/slots/{self.slot0.id}/",
            {"end": "08:50"},
            format="json",
        )
        self.assertEqual(r_patch.status_code, 200)

        # Solver trata slots sobrepostos no mesmo dia como conflitantes
        slots_data = [
            {"id": 1, "weekday": 0, "start": "08:00:00", "end": "09:00:00", "duration_mins": 60},
            {"id": 2, "weekday": 0, "start": "08:30:00", "end": "09:30:00", "duration_mins": 60},
        ]
        subjects_data = [
            {
                "id": 10, "name": "Subj A", "code": "SA", "course_id": 1, "course_name": "C1",
                "weekly_lessons": 2, "preferred_days": [0], "qualified_prof_ids": [1],
            }
        ]
        profs_data = [
            {"id": 1, "full_name": "Prof 1", "max_weekly_mins": 240, "available_slot_ids": {1, 2}}
        ]
        solver = HybridTimetableSolver(slots_data, subjects_data, profs_data, mode="hybrid", seed=1)
        res = solver.solve()
        # Como os 2 slots se sobrepõem no mesmo dia, apenas 1 aula pode ser alocada
        self.assertEqual(len(res["alloc"]), 1)
        self.assertEqual(len(res["pending"]), 1)
        # E se um estado forçar ambos os slots sobrepostos, evaluate_detailed acusa conflito
        eval_conflict = solver.evaluate_detailed([(1, 1), (1, 2)])
        self.assertGreater(eval_conflict["course_conflicts"], 0)
        self.assertGreater(eval_conflict["prof_conflicts"], 0)

    def test_bug08_get_professors_me_has_no_write_side_effect_and_profile_me_works_for_coordinator(self):
        self.assertFalse(Professor.objects.filter(user=self.co1).exists())

        # GET /api/professors/?me=1 não deve criar registro Professor colateralmente
        self.as_(self.co1)
        r_get = self.client.get("/api/professors/?me=1")
        self.assertEqual(r_get.status_code, 200)
        self.assertEqual(r_get.data, [])
        self.assertFalse(Professor.objects.filter(user=self.co1).exists())

        # PATCH /api/profile/me/ deve funcionar diretamente para o coordenador ativo (200 OK)
        r_patch = self.client.patch(
            "/api/profile/me/",
            {"full_name": "Coordenador Docente", "institutional_id": "COORD-99"},
            format="json",
        )
        self.assertEqual(r_patch.status_code, 200)
        self.co1.refresh_from_db()
        self.assertEqual(self.co1.first_name, "Coordenador Docente")
        prof_co1 = Professor.objects.get(user=self.co1)
        self.assertEqual(prof_co1.institutional_id, "COORD-99")

    def test_bug09_user_serializer_case_insensitive_duplicate_email(self):
        self.as_(self.mgr)
        # POST com e-mail já existente em caixa alta / com espaços deve retornar 400
        r_post = self.client.post(
            "/api/users/",
            {
                "first_name": "Outro Coord",
                "email": "  CO1_BUG@X.COM  ",
                "role": "coordinator",
                "password": "Senha@12345",
            },
            format="json",
        )
        self.assertEqual(r_post.status_code, 400)
        self.assertIn("email", r_post.data)

        # PATCH tentando renomear e-mail de co2 para o e-mail do gestor em caixa alta deve retornar 400
        r_patch = self.client.patch(
            f"/api/users/{self.co2.id}/",
            {"email": "  MGR_BUG@X.COM  "},
            format="json",
        )
        self.assertEqual(r_patch.status_code, 400)
        self.assertIn("email", r_patch.data)

    def test_native_accounts_seed_counts_and_courses(self):
        from django.core.management import call_command

        # Cria conta extra que não pertence às nativas para garantir que seja removida
        mkuser("extra_invalido@x.com", "professor", "Conta Antiga")

        call_command("seed_demo", force=True)

        self.assertFalse(User.objects.filter(email="extra_invalido@x.com").exists())
        self.assertEqual(User.objects.count(), 21)

        # 1 conta de gestor, 2 de coordenador e 18 de professor
        self.assertEqual(User.objects.filter(role="manager", is_active=True).count(), 1)
        self.assertEqual(User.objects.filter(role="coordinator", is_active=True).count(), 2)
        self.assertEqual(User.objects.filter(role="professor", is_active=True).count(), 18)
        self.assertEqual(Professor.objects.filter(is_active=True, user__role="professor").count(), 18)

        mgr = User.objects.get(email="gestor@demo.com")
        coord1 = User.objects.get(email="coord@demo.com")
        coord2 = User.objects.get(email="coord2@demo.com")

        # Coordenadora 1 com 2 cursos (SI e CC) e Coordenador 2 com 1 só curso (ES)
        self.assertEqual(Course.objects.filter(coordinator=coord1, is_active=True).count(), 2)
        self.assertEqual(Course.objects.filter(coordinator=coord2, is_active=True).count(), 1)

        # Dashboard do gestor reflete exatamente 2 coordenadores e 18 professores ativos
        self.as_(mgr)
        mgr_cards = {c["label"]: c["value"] for c in self.client.get("/api/dashboard/").data["cards"]}
        self.assertEqual(mgr_cards["Coordenadores"], 2)
        self.assertEqual(mgr_cards["Professores ativos"], 18)

        # Coordenador 2 gera e publica a grade de Engenharia de Software (ES) com 100% de alocação
        self.as_(coord2)
        c_es = Course.objects.get(code="ES")
        r_es = self.client.post("/api/schedules/generate/", {"algorithm": "hybrid", "course_id": c_es.id, "seed": 42}, format="json")
        self.assertEqual(r_es.status_code, 201, r_es.data)
        self.assertEqual(r_es.data["total"], 20)
        self.assertEqual(len(r_es.data["alloc"]), 20)
        self.assertEqual(len(r_es.data["pending"]), 0)
        self.assertEqual(r_es.data["metrics"]["hard_conflicts"], 0)



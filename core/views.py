from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import ProtectedError
from rest_framework.exceptions import APIException, MethodNotAllowed, PermissionDenied
from rest_framework import viewsets, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated, SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import *
from .serializers import *

M, C, P = User.Role.MANAGER, User.Role.COORDINATOR, User.Role.PROFESSOR
ALL = (M, C, P)


class RolePerm(BasePermission):
    """Permissão no servidor: cada ViewSet declara read_roles / write_roles."""
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated and u.is_active): return False
        return u.role in (view.read_roles if request.method in SAFE_METHODS else view.write_roles)


class Conflict(APIException):
    status_code = 409
    default_detail = "Há registros vinculados a este item."


class MgrOrCoord(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_active and u.role in (M, C))


class Base(viewsets.ModelViewSet):
    permission_classes = [RolePerm]
    read_roles, write_roles = ALL, (M,)
    def perform_destroy(self, inst):  # DELETE = exclusão definitiva; desativar é PATCH {is_active:false}
        try:
            inst.delete()
        except ProtectedError:
            raise Conflict("Há registros vinculados a este item. Remova os vínculos antes, ou apenas desative-o.")


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_view(request):
    email, pw = request.data.get("email", ""), request.data.get("password", "")
    u = User.objects.filter(email__iexact=email).first()
    if not (u and u.is_active and u.check_password(pw)):
        return Response({"detail": "E-mail ou senha inválidos."}, status=400)
    token, _ = Token.objects.get_or_create(user=u)
    return Response({"token": token.key, "user": _me(u)})

def _me(u): return {"id": u.id, "name": u.first_name or u.email, "email": u.email, "role": u.role}

@api_view(["POST"])
def logout_view(request):
    Token.objects.filter(user=request.user).delete(); return Response(status=204)

@api_view(["GET"])
def me_view(request): return Response(_me(request.user))


@api_view(["POST"])
def change_password(request):
    cur, new = request.data.get("current", ""), request.data.get("new", "")
    if not request.user.check_password(cur): return Response({"current": "Senha atual incorreta."}, status=400)
    if not new: return Response({"new": "Informe a nova senha."}, status=400)
    request.user.set_password(new); request.user.save()
    return Response({"detail": "Senha alterada."})


class MyProfile(APIView):
    """Professor (ou Coordenador que também leciona) edita seus dados básicos (nome e identificador institucional)."""
    def patch(self, request):
        p = None
        if request.user.is_active:
            if request.user.role == P:
                p = Professor.objects.filter(user=request.user, is_active=True).select_related("user").first()
            elif request.user.role == C:
                p, _ = Professor.objects.get_or_create(user=request.user, defaults={"max_weekly_hours": 16})
                if not p.is_active:
                    p = None
        if not p: return Response({"detail": "Apenas professores."}, status=403)
        name, inst = request.data.get("full_name"), request.data.get("institutional_id")
        if name is not None:
            if not str(name).strip(): return Response({"full_name": "Informe o nome."}, status=400)
            p.user.first_name = str(name).strip(); p.user.save(update_fields=["first_name"])
        if inst is not None:
            p.institutional_id = str(inst).strip()[:30]; p.save(update_fields=["institutional_id"])
        return Response({"full_name": p.user.first_name, "institutional_id": p.institutional_id})


class UserViewSet(Base):
    serializer_class = UserSerializer; search_fields = ["first_name", "email"]
    read_roles = write_roles = (M,)
    queryset = User.objects.select_related("professor").order_by("first_name")
    def perform_destroy(self, inst):
        if inst.pk == self.request.user.pk:
            raise s.ValidationError("Você não pode excluir a si mesmo.")
        inst.delete()


class CourseViewSet(Base):
    serializer_class = CourseSerializer; search_fields = ["name", "code"]; write_roles = (C,)
    def get_queryset(self):
        qs, u = Course.objects.select_related("coordinator").order_by("name"), self.request.user
        return qs.filter(coordinator=u) if u.role == C else qs
    def perform_create(self, ser):
        u = self.request.user; ser.save(coordinator=u) if u.role == C else ser.save()
    def perform_update(self, ser):
        u = self.request.user; ser.save(coordinator=u) if u.role == C else ser.save()


class SubjectViewSet(Base):
    serializer_class = SubjectSerializer; search_fields = ["name", "code", "course__name"]; write_roles = (C,)
    def get_queryset(self):
        qs, u = Subject.objects.select_related("course").prefetch_related("professors").order_by("name"), self.request.user
        if self.request.query_params.get("mine") == "1":
            qs = qs.filter(professors__user=u)
        elif u.role == C: qs = qs.filter(course__coordinator=u)
        elif u.role == P: qs = qs.filter(professors__user=u)
        course_id = self.request.query_params.get("course")
        if course_id: qs = qs.filter(course_id=course_id)
        return qs


class ProfessorViewSet(Base):
    serializer_class = ProfessorSerializer; search_fields = ["user__first_name", "user__email", "institutional_id"]
    write_roles = (M,)  # contas de professor: só o gestor; coordenador apenas atribui disciplinas
    def get_queryset(self):
        qs, u = Professor.objects.select_related("user").prefetch_related("subjects").order_by("user__first_name"), self.request.user
        if self.request.query_params.get("me") == "1":
            return qs.filter(user=u)
        return qs.filter(user=u) if u.role == P else qs
    def perform_destroy(self, inst):
        inst.user.delete()  # remove também o perfil de professor e sua disponibilidade
    @action(detail=True, methods=["get"], url_path="availability")
    def availability(self, request, pk=None):
        p = self.get_object()
        return Response({"slots": list(p.availability.values_list("slot_id", flat=True))})

    @action(detail=True, methods=["put"], url_path="subjects", permission_classes=[MgrOrCoord])
    def assign(self, request, pk=None):
        """Coordenador atribui disciplinas (só as dos seus cursos) ao professor; vínculos fora do escopo são preservados."""
        p = self.get_object()
        if not p.is_active: return Response({"detail": "Professor inativo."}, status=400)
        ids = request.data.get("subjects")
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            return Response({"subjects": "Envie uma lista de ids."}, status=400)
        scope = Subject.objects.filter(is_active=True)
        if request.user.role == C: scope = scope.filter(course__coordinator=request.user)
        chosen = set(scope.filter(id__in=ids).values_list("id", flat=True))
        if chosen != set(ids): return Response({"subjects": "Há disciplinas inativas ou fora dos seus cursos."}, status=400)
        current = set(p.subjects.filter(id__in=scope.values("id")).values_list("id", flat=True))
        p.subjects.remove(*(current - chosen)); p.subjects.add(*(chosen - current))
        return Response({"subjects": sorted(p.subjects.values_list("id", flat=True))})


class RoomViewSet(Base):
    serializer_class = RoomSerializer; queryset = Room.objects.order_by("name"); search_fields = ["name", "room_type"]
    read_roles = write_roles = (C,)


class SlotViewSet(Base):
    serializer_class = SlotSerializer; queryset = Slot.objects.all()
    def perform_update(self, ser):
        inst = ser.save()
        if not inst.is_active: Availability.objects.filter(slot=inst).delete()


class MyAvailability(APIView):
    permission_classes = [IsAuthenticated]
    def _prof(self, request):
        if request.user.role == P:
            return Professor.objects.filter(user=request.user, is_active=True).first()
        if request.user.role == C:
            p, _ = Professor.objects.get_or_create(user=request.user, defaults={"max_weekly_hours": 16})
            return p if p.is_active else None
        return None
    def get(self, request):
        p = self._prof(request)
        if not p: return Response({"detail": "Apenas professores."}, status=403)
        return Response({"slots": list(p.availability.values_list("slot_id", flat=True))})
    @transaction.atomic
    def put(self, request):
        p = self._prof(request)
        if not p: return Response({"detail": "Apenas professores."}, status=403)
        ids = request.data.get("slots")
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            return Response({"slots": "Envie uma lista de ids."}, status=400)
        valid = set(Slot.objects.filter(id__in=ids, is_active=True).values_list("id", flat=True))
        if valid != set(ids): return Response({"slots": "Há horários inválidos ou inativos."}, status=400)
        p.availability.exclude(slot_id__in=valid).delete()
        have = set(p.availability.values_list("slot_id", flat=True))
        Availability.objects.bulk_create([Availability(professor=p, slot_id=i) for i in valid - have])
        return Response({"slots": sorted(valid)})


@api_view(["GET"])
def dashboard(request):
    u = request.user
    if u.role == M:
        cards = [("Coordenadores", User.objects.filter(role=C, is_active=True).count()),
                 ("Professores ativos", Professor.objects.filter(is_active=True, user__role=P).count()),
                 ("Horários (slots)", Slot.objects.filter(is_active=True).count())]
    elif u.role == C:
        subs = Subject.objects.filter(course__coordinator=u, is_active=True)
        cards = [("Meus cursos", Course.objects.filter(coordinator=u, is_active=True).count()), ("Disciplinas", subs.count()),
                 ("Professores ativos", Professor.objects.filter(is_active=True, user__role=P).count()),
                 ("Professores com disponibilidade", Professor.objects.filter(is_active=True, user__role=P, availability__isnull=False).distinct().count())]
    else:
        p = Professor.objects.filter(user=u).first()
        cards = [("Disciplinas habilitadas", p.subjects.filter(is_active=True).count() if p else 0),
                 ("Horários marcados como disponíveis", p.availability.count() if p else 0),
                 ("Carga semanal máxima (h)", p.max_weekly_hours if p else 0)]
    return Response({"cards": [{"label": l, "value": v} for l, v in cards]})


def _parse_time_mins(val):
    if val is None:
        return None
    if hasattr(val, "hour"):
        return val.hour * 60 + val.minute
    parts = str(val).split(":")
    if len(parts) >= 2:
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            return None
    return None


class ScheduleViewSet(Base):
    """Gerencia propostas de grade horária geradas pelo motor Híbrido (SA + Tabu Search) por curso."""
    serializer_class = ScheduleProposalSerializer
    read_roles, write_roles = ALL, (M, C)

    def get_queryset(self):
        u = self.request.user
        qs = ScheduleProposal.objects.select_related("course").all()
        if u.role == P:
            return qs.filter(status=ScheduleProposal.Status.PUBLISHED)
        if u.role == C:
            qs = qs.filter(
                models.Q(course__isnull=True, created_by=u)
                | models.Q(course__coordinator=u)
                | models.Q(status=ScheduleProposal.Status.PUBLISHED)
            )
        course_id = self.request.query_params.get("course_id")
        if course_id:
            qs = qs.filter(course_id=course_id)
        return qs

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def partial_update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def _check_coord_ownership(self, proposal):
        u = self.request.user
        if u.role == C:
            if proposal.course_id is not None:
                if not proposal.course or proposal.course.coordinator_id != u.id:
                    raise PermissionDenied("Você só pode gerenciar propostas de cursos sob sua coordenação.")
            else:
                if proposal.created_by_id != u.id:
                    raise PermissionDenied("Você só pode gerenciar propostas criadas por você.")

    def perform_destroy(self, inst):
        self._check_coord_ownership(inst)
        super().perform_destroy(inst)

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request):
        from .solver import HybridTimetableSolver
        from collections import defaultdict

        seed = request.data.get("seed")
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, (int, float, str))):
            return Response({"seed": "Seed inválido."}, status=400)

        u = request.user
        slots_qs = Slot.objects.filter(is_active=True).order_by("weekday", "start")
        subs_qs = Subject.objects.filter(is_active=True, course__is_active=True).select_related("course").prefetch_related("professors")
        if u.role == C:
            subs_qs = subs_qs.filter(course__coordinator=u)

        course_id = request.data.get("course_id")
        course_obj = None
        if course_id:
            course_qs = Course.objects.filter(pk=course_id, is_active=True)
            if u.role == C:
                course_qs = course_qs.filter(coordinator=u)
            course_obj = course_qs.first()
            if not course_obj:
                return Response({"detail": "Curso inválido ou fora da sua coordenação."}, status=400)
            subs_qs = subs_qs.filter(course_id=course_obj.id)

        profs_qs = Professor.objects.filter(is_active=True, user__is_active=True).select_related("user").prefetch_related("availability", "subjects")

        slots_list = list(slots_qs)
        subs_list = list(subs_qs)
        profs_list = list(profs_qs)

        if not slots_list:
            return Response({"detail": "Nenhum horário ativo cadastrado."}, status=400)
        if not subs_list:
            return Response({"detail": "Nenhuma disciplina ativa encontrada neste curso para gerar a grade."}, status=400)
        if not profs_list:
            return Response({"detail": "Nenhum professor ativo cadastrado."}, status=400)

        slots_data = []
        slots_serial = []
        slot_dur_map = {}
        slot_meta = {}
        for sl in slots_list:
            s_min = sl.start.hour * 60 + sl.start.minute
            e_min = sl.end.hour * 60 + sl.end.minute
            dur = max(1, e_min - s_min)
            slot_dur_map[sl.id] = dur
            slot_meta[sl.id] = (sl.weekday, s_min, e_min, dur)
            start_str = sl.start.strftime("%H:%M:%S")
            end_str = sl.end.strftime("%H:%M:%S")
            slots_data.append({
                "id": sl.id,
                "weekday": sl.weekday,
                "start": start_str,
                "end": end_str,
                "duration_mins": dur,
            })
            slots_serial.append({
                "id": sl.id,
                "weekday": sl.weekday,
                "start": start_str,
                "end": end_str,
            })

        # Respeita sempre os horários e cargas já ocupados por grades PUBLICADAS de OUTROS cursos!
        target_course_ids = {s.course_id for s in subs_list}
        busy_prof_slots = defaultdict(set)
        busy_prof_mins = defaultdict(int)
        counted_prof_allocs = defaultdict(set)
        other_published = ScheduleProposal.objects.filter(
            status=ScheduleProposal.Status.PUBLISHED
        ).exclude(course_id__in=target_course_ids)
        for pub in other_published:
            for item in (pub.alloc or []):
                item_cid = item.get("courseId") if item.get("courseId") is not None else pub.course_id
                if item_cid in target_course_ids:
                    continue
                pid = item.get("professorId")
                sid = item.get("slotId")
                if not pid or not sid:
                    continue
                if sid in slot_meta:
                    w, s_min, e_min, dur = slot_meta[sid]
                else:
                    w = item.get("weekday")
                    s_min = _parse_time_mins(item.get("start"))
                    e_min = _parse_time_mins(item.get("end"))
                    dur = max(1, e_min - s_min) if (s_min is not None and e_min is not None) else 50
                if sid not in counted_prof_allocs[pid]:
                    counted_prof_allocs[pid].add(sid)
                    busy_prof_mins[pid] += dur
                busy_prof_slots[pid].add(sid)
                if w is not None and s_min is not None and e_min is not None:
                    for sl_id, (sl_w, sl_s, sl_e, _) in slot_meta.items():
                        if sl_w == w and sl_s < e_min and sl_e > s_min:
                            busy_prof_slots[pid].add(sl_id)

        active_prof_ids = {p.id for p in profs_list}
        subjects_data = []
        for sb in subs_list:
            qual_ids = [p.id for p in sb.professors.all() if p.id in active_prof_ids]
            subjects_data.append({
                "id": sb.id,
                "name": sb.name,
                "code": sb.code,
                "course_id": sb.course_id,
                "course_name": sb.course.name,
                "weekly_lessons": sb.weekly_lessons,
                "lesson_minutes": sb.lesson_minutes,
                "preferred_days": sb.preferred_days or [],
                "qualified_prof_ids": qual_ids,
            })

        professors_data = []
        for p in profs_list:
            raw_avail_ids = {a.slot_id for a in p.availability.all()}
            avail_ids = raw_avail_ids - busy_prof_slots[p.id]
            rem_mins = max(0, p.max_weekly_hours * 60 - busy_prof_mins[p.id])
            professors_data.append({
                "id": p.id,
                "full_name": p.user.first_name or p.user.email,
                "max_weekly_mins": rem_mins,
                "available_slot_ids": avail_ids,
                "busy_other_course_slots": len(raw_avail_ids & busy_prof_slots[p.id]),
            })

        algo = str(request.data.get("algorithm") or "hybrid").lower()
        if algo not in ("hybrid", "sa", "tabu"):
            algo = "hybrid"

        try:
            solver = HybridTimetableSolver(
                slots=slots_data,
                subjects=subjects_data,
                professors=professors_data,
                mode=algo,
                seed=seed,
            )
            result = solver.solve()
        except (ValueError, TypeError):
            return Response({"seed": "Seed inválido."}, status=400)

        scope_label = course_obj.name if course_obj else ("Meus cursos" if u.role == C else "Todos os cursos")

        with transaction.atomic():
            proposal = ScheduleProposal.objects.create(
                created_by=u,
                course=course_obj,
                by_name=u.first_name or u.email,
                scope=scope_label,
                algorithm=algo,
                status=ScheduleProposal.Status.DRAFT,
                total=result["total"],
                alloc=result["alloc"],
                pending=result["pending"],
                slots=slots_serial,
                metrics=result["metrics"],
            )

            # Keep up to 10 proposals in history per user and course (preserving published)
            hist_qs = ScheduleProposal.objects.filter(created_by=u, course=course_obj).exclude(
                status=ScheduleProposal.Status.PUBLISHED
            )
            old_ids = list(hist_qs.order_by("-created_at", "-id").values_list("id", flat=True)[10:])
            if old_ids:
                ScheduleProposal.objects.filter(id__in=old_ids).delete()

        return Response(ScheduleProposalSerializer(proposal).data, status=201)

    @action(detail=True, methods=["post"], url_path="publish")
    @transaction.atomic
    def publish(self, request, pk=None):
        from collections import defaultdict

        proposal = self.get_object()
        self._check_coord_ownership(proposal)

        other_published = ScheduleProposal.objects.filter(
            status=ScheduleProposal.Status.PUBLISHED
        ).exclude(pk=proposal.pk)
        if proposal.course_id is not None:
            other_published = other_published.exclude(course_id=proposal.course_id)
        else:
            other_published = other_published.exclude(course__isnull=True)
        other_published = list(other_published)

        slot_meta = {}
        for sl in Slot.objects.all():
            s_min = sl.start.hour * 60 + sl.start.minute
            e_min = sl.end.hour * 60 + sl.end.minute
            slot_meta[sl.id] = (sl.weekday, s_min, e_min, max(1, e_min - s_min))

        def _slot_info(item):
            sid = item.get("slotId")
            if sid in slot_meta:
                return slot_meta[sid]
            w = item.get("weekday")
            s_min = _parse_time_mins(item.get("start"))
            e_min = _parse_time_mins(item.get("end"))
            dur = max(1, e_min - s_min) if (s_min is not None and e_min is not None) else 50
            return (w, s_min, e_min, dur)

        proposal_alloc = proposal.alloc or []
        proposal_course_ids = set()
        if proposal.course_id is not None:
            proposal_course_ids.add(proposal.course_id)
        for item in proposal_alloc:
            cid = item.get("courseId")
            if cid is not None:
                proposal_course_ids.add(cid)

        other_prof_allocs = defaultdict(list)
        other_prof_mins = defaultdict(int)
        other_counted_slots = defaultdict(set)

        for pub in other_published:
            for other_item in (pub.alloc or []):
                other_cid = other_item.get("courseId") if other_item.get("courseId") is not None else pub.course_id
                pid = other_item.get("professorId")
                sid = other_item.get("slotId")
                if not pid:
                    continue
                w, s_min, e_min, dur = _slot_info(other_item)
                other_prof_allocs[pid].append((other_cid, sid, w, s_min, e_min))
                if other_cid is not None and other_cid in proposal_course_ids:
                    continue
                dedup_key = (other_cid, sid, w, s_min, e_min)
                if dedup_key not in other_counted_slots[pid]:
                    other_counted_slots[pid].add(dedup_key)
                    other_prof_mins[pid] += dur

        proposal_prof_mins = defaultdict(int)
        for item in proposal_alloc:
            pid = item.get("professorId")
            sid = item.get("slotId")
            if not pid:
                continue
            cur_cid = item.get("courseId") if item.get("courseId") is not None else proposal.course_id
            w, s_min, e_min, dur = _slot_info(item)
            proposal_prof_mins[pid] += dur

            for other_cid, other_sid, other_w, other_s, other_e in other_prof_allocs.get(pid, []):
                if cur_cid is not None and other_cid is not None and cur_cid == other_cid:
                    continue
                if (sid is not None and sid == other_sid) or (
                    w is not None and other_w is not None and w == other_w
                    and s_min is not None and e_min is not None
                    and other_s is not None and other_e is not None
                    and s_min < other_e and e_min > other_s
                ):
                    return Response(
                        {"detail": "Conflito de horário: professor já está alocado neste horário em outra grade publicada."},
                        status=409,
                    )

        if proposal_prof_mins:
            prof_max_map = {
                p.id: p.max_weekly_hours * 60
                for p in Professor.objects.filter(id__in=proposal_prof_mins.keys())
            }
            for pid, mins in proposal_prof_mins.items():
                max_mins = prof_max_map.get(pid)
                if max_mins is not None and (other_prof_mins[pid] + mins) > max_mins:
                    return Response(
                        {"detail": "Sobrecarga de carga horária: professor excede a carga semanal máxima somando outras grades publicadas."},
                        status=409,
                    )

        # Arquiva apenas a grade publicada anterior do MESMO curso (permitindo 1 grade publicada por curso!)
        same_scope = ScheduleProposal.objects.filter(status=ScheduleProposal.Status.PUBLISHED).exclude(pk=proposal.pk)
        if proposal.course_id:
            same_scope = same_scope.filter(course_id=proposal.course_id)
        else:
            same_scope = same_scope.filter(course__isnull=True)
        same_scope.update(status=ScheduleProposal.Status.ARCHIVED)

        proposal.status = ScheduleProposal.Status.PUBLISHED
        proposal.save(update_fields=["status"])
        return Response(ScheduleProposalSerializer(proposal).data)

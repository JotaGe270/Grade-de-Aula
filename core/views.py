from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import ProtectedError
from rest_framework.exceptions import APIException
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
    """Professor edita só seus dados básicos (nome e identificador institucional)."""
    def patch(self, request):
        p = Professor.objects.filter(user=request.user, is_active=True).select_related("user").first() if request.user.role == P else None
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
        if u.role == C: return qs.filter(course__coordinator=u)
        if u.role == P: return qs.filter(professors__user=u)
        return qs


class ProfessorViewSet(Base):
    serializer_class = ProfessorSerializer; search_fields = ["user__first_name", "user__email", "institutional_id"]
    write_roles = (M,)  # contas de professor: só o gestor; coordenador apenas atribui disciplinas
    def get_queryset(self):
        qs, u = Professor.objects.select_related("user").prefetch_related("subjects").order_by("user__first_name"), self.request.user
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
        return Professor.objects.filter(user=request.user, is_active=True).first() if request.user.role == P else None
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
                 ("Professores ativos", Professor.objects.filter(is_active=True).count()),
                 ("Horários (slots)", Slot.objects.filter(is_active=True).count())]
    elif u.role == C:
        subs = Subject.objects.filter(course__coordinator=u, is_active=True)
        cards = [("Meus cursos", Course.objects.filter(coordinator=u, is_active=True).count()), ("Disciplinas", subs.count()),
                 ("Professores ativos", Professor.objects.filter(is_active=True).count()),
                 ("Professores com disponibilidade", Professor.objects.filter(is_active=True, availability__isnull=False).distinct().count())]
    else:
        p = Professor.objects.filter(user=u).first()
        cards = [("Disciplinas habilitadas", p.subjects.filter(is_active=True).count() if p else 0),
                 ("Horários marcados como disponíveis", p.availability.count() if p else 0),
                 ("Carga semanal máxima (h)", p.max_weekly_hours if p else 0)]
    return Response({"cards": [{"label": l, "value": v} for l, v in cards]})

from django.db import transaction
from rest_framework.authtoken.models import Token
from rest_framework import serializers as s
from .models import *


class UserSerializer(s.ModelSerializer):
    password = s.CharField(write_only=True, required=False)
    professor_id = s.SerializerMethodField()
    class Meta:
        model = User
        fields = ["id", "first_name", "email", "role", "is_active", "password", "professor_id"]
    def get_professor_id(self, obj):
        try: return obj.professor.id
        except Professor.DoesNotExist: return None
    def validate_role(self, v):
        if v == User.Role.PROFESSOR:
            raise s.ValidationError("Professores são criados em Professores.")
        return v
    def create(self, vd):
        pw = vd.pop("password", None)
        if not pw:
            raise s.ValidationError({"password": "Obrigatório."})
        return User.objects.create_user(username=vd["email"], password=pw, **vd)
    def update(self, inst, vd):
        pw = vd.pop("password", None)
        for k, v in vd.items(): setattr(inst, k, v)
        if "email" in vd: inst.username = vd["email"]
        if vd.get("is_active") is False: Token.objects.filter(user=inst).delete()
        if pw: inst.set_password(pw)
        inst.save(); return inst


class CourseSerializer(s.ModelSerializer):
    coordinator = s.PrimaryKeyRelatedField(queryset=User.objects.filter(role="coordinator"), allow_null=True, required=False)
    coordinator_name = s.CharField(source="coordinator.first_name", read_only=True, default="")
    class Meta:
        model = Course
        fields = ["id", "name", "code", "description", "coordinator", "coordinator_name", "is_active"]


class SubjectSerializer(s.ModelSerializer):
    course_name = s.CharField(source="course.name", read_only=True)
    professors = s.PrimaryKeyRelatedField(many=True, read_only=True)
    preferred_days = s.ListField(child=s.IntegerField(min_value=0, max_value=5), required=False)
    class Meta:
        model = Subject
        fields = ["id", "name", "code", "course", "course_name", "student_count", "weekly_lessons",
                  "lesson_minutes", "preferred_days", "professors", "is_active"]
    def validate_course(self, c):
        u = self.context["request"].user
        if u.role == User.Role.COORDINATOR and c.coordinator_id != u.id:
            raise s.ValidationError("Este curso não está sob sua responsabilidade.")
        return c


class ProfessorSerializer(s.ModelSerializer):
    full_name = s.CharField(source="user.first_name")
    email = s.EmailField(source="user.email")
    password = s.CharField(write_only=True, required=False)
    subjects = s.PrimaryKeyRelatedField(many=True, queryset=Subject.objects.all(), required=False)
    availability_count = s.SerializerMethodField()
    class Meta:
        model = Professor
        fields = ["id", "full_name", "email", "password", "institutional_id", "max_weekly_hours", "subjects", "availability_count", "is_active"]
    def get_availability_count(self, obj): return obj.availability.count()
    def validate_email(self, v):
        qs = User.objects.filter(email__iexact=v)
        if self.instance: qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists(): raise s.ValidationError("Já existe usuário com este e-mail.")
        return v
    def validate_subjects(self, subs):
        if any(not x.is_active for x in subs): raise s.ValidationError("Disciplina inativa.")
        return subs
    @transaction.atomic
    def create(self, vd):
        ud, pw, subs = vd.pop("user"), vd.pop("password", None), vd.pop("subjects", [])
        if not pw: raise s.ValidationError({"password": "Obrigatório."})
        user = User.objects.create_user(username=ud["email"], email=ud["email"], first_name=ud["first_name"],
                                        password=pw, role=User.Role.PROFESSOR)
        p = Professor.objects.create(user=user, **vd); p.subjects.set(subs); return p
    @transaction.atomic
    def update(self, inst, vd):
        ud, pw, subs = vd.pop("user", {}), vd.pop("password", None), vd.pop("subjects", None)
        u = inst.user
        if "first_name" in ud: u.first_name = ud["first_name"]
        if "email" in ud: u.email = u.username = ud["email"]
        if pw: u.set_password(pw)
        if "is_active" in vd: u.is_active = vd["is_active"]
        u.save()
        for k, v in vd.items(): setattr(inst, k, v)
        inst.save()
        if subs is not None: inst.subjects.set(subs)
        return inst


class RoomSerializer(s.ModelSerializer):
    class Meta:
        model = Room; fields = "__all__"


class SlotSerializer(s.ModelSerializer):
    class Meta:
        model = Slot; fields = "__all__"
    def validate(self, d):
        start, end = d.get("start", getattr(self.instance, "start", None)), d.get("end", getattr(self.instance, "end", None))
        if start and end and end <= start: raise s.ValidationError("O fim deve ser depois do início.")
        return d

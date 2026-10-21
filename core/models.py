from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models


class User(AbstractUser):
    """username == email. Perfil define as permissões (RBAC)."""
    class Role(models.TextChoices):
        MANAGER = "manager", "Gestor"
        COORDINATOR = "coordinator", "Coordenador"
        PROFESSOR = "professor", "Professor"
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.PROFESSOR)


class Course(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, unique=True)
    description = models.TextField(blank=True)
    coordinator = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="courses")
    is_active = models.BooleanField(default=True)


class Subject(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, unique=True)
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="subjects")
    student_count = models.PositiveIntegerField(default=30, validators=[MinValueValidator(1)])
    weekly_lessons = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    lesson_minutes = models.PositiveIntegerField(default=50, validators=[MinValueValidator(1)])
    preferred_days = models.JSONField(default=list, blank=True)  # [0..5]; preferência, não restrição
    is_active = models.BooleanField(default=True)


class Professor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="professor")
    institutional_id = models.CharField(max_length=30, blank=True)
    max_weekly_hours = models.PositiveIntegerField(default=20, validators=[MinValueValidator(1)])
    subjects = models.ManyToManyField(Subject, blank=True, related_name="professors")
    is_active = models.BooleanField(default=True)


class Room(models.Model):
    name = models.CharField(max_length=60, unique=True)
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    room_type = models.CharField(max_length=40, blank=True)
    resources = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)


class Slot(models.Model):
    weekday = models.PositiveSmallIntegerField(choices=[(i, d) for i, d in enumerate(
        ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"])])
    start = models.TimeField()
    end = models.TimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("weekday", "start", "end")
        ordering = ["weekday", "start"]


class Availability(models.Model):
    """Existir uma linha = professor disponível naquele slot (não é alocação)."""
    professor = models.ForeignKey(Professor, on_delete=models.CASCADE, related_name="availability")
    slot = models.ForeignKey(Slot, on_delete=models.CASCADE, related_name="+")

    class Meta:
        unique_together = ("professor", "slot")

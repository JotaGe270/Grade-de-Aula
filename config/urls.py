from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.http import HttpResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from pathlib import Path
from core import views as v

router = DefaultRouter()
router.register("users", v.UserViewSet, "user")
router.register("courses", v.CourseViewSet, "course")
router.register("subjects", v.SubjectViewSet, "subject")
router.register("professors", v.ProfessorViewSet, "professor")
router.register("rooms", v.RoomViewSet, "room")
router.register("slots", v.SlotViewSet, "slot")

def index(request):
    return HttpResponse((Path(__file__).resolve().parent.parent / "frontend" / "index.html").read_text("utf-8"))

urlpatterns = [
    path("api/auth/login/", v.login_view), path("api/auth/logout/", v.logout_view), path("api/auth/me/", v.me_view),
    path("api/auth/password/", v.change_password), path("api/profile/me/", v.MyProfile.as_view()),
    path("api/availability/me/", v.MyAvailability.as_view()), path("api/dashboard/", v.dashboard),
    path("api/", include(router.urls)), path("", index),
] + staticfiles_urlpatterns()

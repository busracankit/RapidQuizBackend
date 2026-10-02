from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.leaderboard.views import LeaderboardView, SessionScoreView
from apps.quiz.views import (
    CategoryListView,
    SessionAnswerView,
    SessionCreateView,
    SessionCurrentView,
    SessionResultView,
)
from config.views import HealthView

admin.site.site_header = "Rapid Quiz Yönetimi"
admin.site.site_title = "Rapid Quiz"
admin.site.index_title = "İçerik ve oyun verileri"

api_v1 = [
    path("categories/", CategoryListView.as_view(), name="categories"),
    path("sessions/", SessionCreateView.as_view(), name="session-create"),
    path(
        "sessions/<str:session_id>/current/", SessionCurrentView.as_view(), name="session-current"
    ),
    path("sessions/<str:session_id>/answers/", SessionAnswerView.as_view(), name="session-answer"),
    path("sessions/<str:session_id>/result/", SessionResultView.as_view(), name="session-result"),
    path("sessions/<str:session_id>/score/", SessionScoreView.as_view(), name="session-score"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("health/", HealthView.as_view(), name="health"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/", include((api_v1, "v1"))),
]

handler404 = "config.api.api_not_found"

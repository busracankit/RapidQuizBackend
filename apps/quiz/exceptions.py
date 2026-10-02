"""Servis katmanının fırlattığı, API'de sabit hata formatına çevrilen hatalar.

Hata formatı: {"error": {"code": "<code>", "message": "<mesaj>"}}
"""


class QuizError(Exception):
    status_code = 400
    code = "quiz_error"
    message = "İşlem gerçekleştirilemedi."

    def __init__(self, message: str | None = None):
        self.message = message or self.message
        super().__init__(self.message)


class CategoryNotFound(QuizError):
    status_code = 404
    code = "category_not_found"
    message = "Kategori bulunamadı."


class NotEnoughQuestions(QuizError):
    status_code = 409
    code = "not_enough_questions"
    message = "Bu kategoride henüz yeterli soru yok."


class SessionNotFound(QuizError):
    status_code = 404
    code = "session_not_found"
    message = "Oturum bulunamadı."


class InvalidSessionToken(QuizError):
    status_code = 403
    code = "invalid_session_token"
    message = "Oturum anahtarı eksik ya da geçersiz."


class SessionExpired(QuizError):
    status_code = 410
    code = "session_expired"
    message = "Oturumun süresi doldu. Yeni bir oyun başlatın."


class SessionFinished(QuizError):
    status_code = 409
    code = "session_finished"
    message = "Bu oturumdaki tüm sorular cevaplandı."


class SessionNotFinished(QuizError):
    status_code = 409
    code = "session_not_finished"
    message = "Oturum henüz tamamlanmadı."


class QuestionMismatch(QuizError):
    status_code = 409
    code = "question_mismatch"
    message = "Gönderilen soru, oturumdaki güncel soru değil."


class InvalidChoice(QuizError):
    status_code = 400
    code = "invalid_choice"
    message = "Geçersiz şık."


class ScoreAlreadySaved(QuizError):
    status_code = 409
    code = "score_already_saved"
    message = "Bu oturumun skoru zaten kaydedildi."


class InvalidPlayerName(QuizError):
    status_code = 400
    code = "invalid_player_name"
    message = "İsim geçersiz."

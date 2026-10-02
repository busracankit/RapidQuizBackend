from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count, Q

from .models import CHOICES_PER_QUESTION, Category, Choice, Question, QuizSession, SessionQuestion

# --------------------------------------------------------------------------- içerik


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "color", "order", "is_active", "active_question_count")
    list_editable = ("order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_active_questions=Count("questions", filter=Q(questions__is_active=True)))
        )

    @admin.display(description="aktif soru", ordering="_active_questions")
    def active_question_count(self, obj):
        return obj._active_questions


class ChoiceInlineFormSet(forms.BaseInlineFormSet):
    """Soru başına tam 4 şık ve tam 1 doğru şık zorunludur."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        live = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE", False)]
        if len(live) != CHOICES_PER_QUESTION:
            raise ValidationError(f"Her sorunun tam {CHOICES_PER_QUESTION} şıkkı olmalı.")
        correct = sum(1 for f in live if f.cleaned_data.get("is_correct"))
        if correct != 1:
            raise ValidationError("Her sorunun tam 1 doğru şıkkı olmalı.")
        texts = [f.cleaned_data["text"].strip().casefold() for f in live]
        if len(set(texts)) != len(texts):
            raise ValidationError("Şık metinleri birbirinden farklı olmalı.")


class ChoiceForm(forms.ModelForm):
    class Meta:
        model = Choice
        fields = ("order", "text", "is_correct")

    def validate_constraints(self):
        # "Tek doğru şık" kısıtı formset.clean() içinde tüm şıklar birlikte doğrulanır.
        # Form tek başına kontrol etseydi, doğru şık değiştirilirken DB'deki eski doğru
        # şıkkı görüp yanlışlıkla hata verirdi. Bu yüzden `question` alanlı kısıtlar atlanır.
        exclude = self._get_validation_exclusions() | {"question"}
        try:
            self.instance.validate_constraints(exclude=exclude)
        except ValidationError as e:
            self._update_errors(e)


class ChoiceInline(admin.TabularInline):
    model = Choice
    form = ChoiceForm
    formset = ChoiceInlineFormSet
    extra = 0
    min_num = CHOICES_PER_QUESTION
    max_num = CHOICES_PER_QUESTION
    validate_min = True
    validate_max = True
    fields = ("order", "text", "is_correct")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    inlines = [ChoiceInline]
    list_display = ("text", "category", "difficulty", "is_active", "updated_at")
    list_filter = ("category", "difficulty", "is_active")
    search_fields = ("text", "choices__text")
    list_select_related = ("category",)
    list_per_page = 50
    actions = ("activate", "deactivate")
    fields = ("category", "text", "difficulty", "explanation", "is_active")

    def save_formset(self, request, form, formset, change):
        if formset.model is not Choice:
            return super().save_formset(request, form, formset, change)
        # Doğru şık değiştirilirken "tek doğru şık" kısıtı ihlal edilmesin diye önce
        # silinenler, sonra doğru=False olanlar, en son doğru şık kaydedilir.
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for obj in sorted(instances, key=lambda c: c.is_correct):
            obj.save()
        formset.save_m2m()

    @admin.action(description="Seçili soruları aktifleştir")
    def activate(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} soru aktifleştirildi.")

    @admin.action(description="Seçili soruları pasifleştir")
    def deactivate(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} soru pasifleştirildi.")


# --------------------------------------------------------------------------- oyun (salt okunur)


class ReadOnlyAdminMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class SessionQuestionInline(ReadOnlyAdminMixin, admin.TabularInline):
    model = SessionQuestion
    extra = 0
    can_delete = False
    fields = (
        "order",
        "question",
        "selected_choice",
        "is_correct",
        "timed_out",
        "response_ms",
        "points",
        "served_at",
        "answered_at",
    )
    readonly_fields = fields


@admin.register(QuizSession)
class QuizSessionAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    inlines = [SessionQuestionInline]
    list_display = (
        "id",
        "category",
        "status",
        "current_index",
        "score",
        "correct_count",
        "client_type",
        "started_at",
    )
    list_filter = ("status", "category", "client_type")
    date_hierarchy = "started_at"
    list_select_related = ("category",)
    exclude = ("token_hash",)

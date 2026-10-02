"""5 başlangıç kategorisini oluşturur (dokümandaki renk ve ikonlarla)."""

from django.db import migrations

CATEGORIES = [
    {
        "slug": "yazilim",
        "name": "Yazılım",
        "description": "Diller, algoritmalar ve yazılım geliştirme pratikleri.",
        "icon": "code",
        "color": "#3B82F6",
        "order": 1,
    },
    {
        "slug": "yapay-zeka",
        "name": "Yapay Zeka",
        "description": "Makine öğrenmesi, derin öğrenme ve yapay zekanın tarihi.",
        "icon": "brain",
        "color": "#A855F7",
        "order": 2,
    },
    {
        "slug": "bilgisayar-muhendisligi",
        "name": "Bilgisayar Mühendisliği",
        "description": "Donanım, işletim sistemleri, ağlar ve mimari.",
        "icon": "cpu",
        "color": "#F97316",
        "order": 3,
    },
    {
        "slug": "ulkeler",
        "name": "Ülkeler",
        "description": "Başkentler, bayraklar, coğrafya ve kültür.",
        "icon": "globe",
        "color": "#10B981",
        "order": 4,
    },
    {
        "slug": "fizik",
        "name": "Fizik",
        "description": "Mekanikten kuantuma temel fizik bilgisi.",
        "icon": "atom",
        "color": "#06B6D4",
        "order": 5,
    },
]


def seed(apps, schema_editor):
    Category = apps.get_model("quiz", "Category")
    for data in CATEGORIES:
        slug = data["slug"]
        defaults = {k: v for k, v in data.items() if k != "slug"}
        Category.objects.get_or_create(slug=slug, defaults=defaults)


def unseed(apps, schema_editor):
    Category = apps.get_model("quiz", "Category")
    Category.objects.filter(
        slug__in=[c["slug"] for c in CATEGORIES], questions__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("quiz", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]

from datetime import date

from decouple import config
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.vision.models import Campo, Modulo, Vuelo


class Command(BaseCommand):
    help = "Crea un superusuario demo y datos de ejemplo (idempotente)."

    def handle(self, *args, **options) -> None:
        User = get_user_model()

        username = config("DEMO_USER", default="admin")
        password = config("DEMO_PASSWORD", default="admin12345")
        email = config("DEMO_EMAIL", default="admin@example.com")

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"Superusuario demo creado: {username}")
            )
        else:
            self.stdout.write(f"Superusuario demo ya existe: {username}")

        if Campo.objects.exists():
            self.stdout.write("Datos demo ya presentes, se omite la siembra.")
            return

        campo = Campo.objects.create(
            nombre="Campo Norte",
            descripcion="Campo de demostración para detección de plantas.",
            ubicacion="Mendoza, Argentina",
            latitud=-32.8895,
            longitud=-68.8458,
        )
        modulo = Modulo.objects.create(
            campo=campo,
            nombre="Módulo A",
            descripcion="Módulo de ejemplo.",
        )
        Vuelo.objects.create(
            modulo=modulo,
            nombre="Vuelo inicial",
            fecha_vuelo=date.today(),
        )
        self.stdout.write(self.style.SUCCESS("Datos demo creados."))
